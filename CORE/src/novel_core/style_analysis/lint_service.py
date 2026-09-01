from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from novel_core.errors import AnalysisCancelledError, ValidationError
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.fingerprints import (
    JsonObject,
    JsonValue,
    fingerprint_json,
)
from novel_core.style_analysis.lint_evidence import build_lint_evidence
from novel_core.style_analysis.lint_repository import (
    FindingRecord,
    LintRepository,
    LintRunRecord,
    json_text,
)
from novel_core.style_analysis.metrics import METRIC_DEFINITIONS
from novel_core.style_analysis.profile_service import ProfileService
from novel_core.style_analysis.semantic_metric_support import enabled_person
from novel_core.style_analysis.semantic_scene import (
    resolve_scene_semantics,
    scene_axis_values,
)
from novel_core.style_analysis.structure_models import SceneRecord
from novel_core.style_analysis.text_service import StyleTextService

_SCENE_AXES = frozenset({"function", "tone", "pace", "information_load", "interaction"})
_ANALYZER_BY_GROUP = {
    "basic": "style-metrics-basic",
    "semantic": "style-metrics-semantic",
}


@dataclass(frozen=True, slots=True)
class LintResult:
    run: LintRunRecord
    findings: tuple[FindingRecord, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    rule: Any
    target_type: str
    target_id: int
    specificity: int


class StyleLintService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._texts = StyleTextService(connection)
        self._profiles = ProfileService(connection)
        self._repository = LintRepository(connection)

    def run(
        self,
        *,
        document_id: int,
        text_revision_id: int,
        structure_revision_id: int,
        profile_id: int,
        profile_version_no: int,
        scene_id: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> LintResult:
        context = self._context(
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            profile_id=profile_id,
            profile_version_no=profile_version_no,
            scene_id=scene_id,
            progress_callback=progress_callback,
            cancellation_probe=cancellation_probe,
        )
        run_id = self._repository.insert_run(
            (
                document_id,
                text_revision_id,
                structure_revision_id,
                profile_id,
                context["version_id"],
                scene_id,
                context["basic_run_id"],
                context["semantic_run_id"],
                context["fingerprint"],
                "running",
                json_text(context["warnings"]),
                context["enabled_count"],
                context["applicable_count"],
                context["missing_count"],
                None,
            )
        )
        savepoint = "style_lint_findings"
        self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            for finding in context["findings"]:
                self._repository.insert_finding((run_id, *finding))
            self._repository.finish_run(run_id, "succeeded")
            self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            self._repository.finish_run(run_id, "failed")
            raise
        run = self._repository.get_run(run_id)
        if run is None:
            raise RuntimeError("lint run retrieval failed")
        return LintResult(run, self._repository.list_findings(run_id))

    def get_run(self, lint_run_id: int) -> LintRunRecord | None:
        return self._repository.get_run(lint_run_id)

    def list_runs(self, document_id: int | None = None) -> tuple[LintRunRecord, ...]:
        return self._repository.list_runs(document_id)

    def list_findings(self, lint_run_id: int) -> tuple[FindingRecord, ...]:
        return self._repository.list_findings(lint_run_id)

    def review_finding(
        self, finding_id: int, status: str, note: str | None
    ) -> FindingRecord:
        if status not in {"acknowledged", "ignored"}:
            raise ValidationError("FINDING_REVIEW_STATUS_INVALID")
        if self._repository.get_finding(finding_id) is None:
            raise ValidationError("FINDING_NOT_FOUND")
        self._repository.add_review(finding_id, status, note)
        finding = self._repository.get_finding(finding_id)
        if finding is None:
            raise RuntimeError("finding retrieval failed")
        return finding

    def is_stale(self, run: LintRunRecord) -> bool:
        document = self._texts.get_document(run.document_id)
        if document is None:
            return True
        if (
            document.current_text_revision_id != run.text_revision_id
            or document.current_structure_revision_id != run.structure_revision_id
        ):
            return True
        context = self._context(
            document_id=run.document_id,
            text_revision_id=run.text_revision_id,
            structure_revision_id=run.structure_revision_id,
            profile_id=run.profile_id,
            profile_version_no=self._profile_version_no(run.profile_version_id),
            scene_id=run.scene_id,
        )
        return bool(context["fingerprint"] != run.input_fingerprint)

    def _context(self, **values: object) -> dict[str, Any]:
        document_id = _positive(values["document_id"], "DOCUMENT_ID_REQUIRED")
        text_id = _positive(values["text_revision_id"], "TEXT_REVISION_ID_REQUIRED")
        structure_id = _positive(
            values["structure_revision_id"], "STRUCTURE_REVISION_ID_REQUIRED"
        )
        profile_id = _positive(values["profile_id"], "PROFILE_ID_REQUIRED")
        version_no = _positive(
            values["profile_version_no"], "PROFILE_VERSION_NO_REQUIRED"
        )
        scene_id = values.get("scene_id")
        if scene_id is not None:
            scene_id = _positive(scene_id, "SCENE_ID_INVALID")
        document = self._texts.get_document(document_id)
        if document is None:
            raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
        if document.current_text_revision_id != text_id:
            raise ValidationError("TEXT_REVISION_NOT_CURRENT")
        if document.current_structure_revision_id != structure_id:
            raise ValidationError("STRUCTURE_REVISION_NOT_CURRENT")
        structure_text = self._connection.execute(
            "SELECT text_revision_id FROM style_structure_revisions WHERE id = ?",
            (structure_id,),
        ).fetchone()
        if structure_text is None or int(structure_text[0]) != text_id:
            raise ValidationError("STRUCTURE_TEXT_REVISION_MISMATCH")
        profile = self._profiles.get_profile(profile_id)
        version = self._profiles.get_version(profile_id, version_no)
        if profile is None:
            raise ValidationError("PROFILE_NOT_FOUND")
        if version is None:
            raise ValidationError("PROFILE_VERSION_NOT_FOUND")
        rules = tuple(
            rule for rule in self._profiles.list_rules(version.id) if rule.enabled
        )
        if scene_id is not None:
            exists = self._connection.execute(
                "SELECT 1 FROM style_scenes WHERE id = ? AND structure_revision_id = ?",
                (scene_id, structure_id),
            ).fetchone()
            if exists is None:
                raise ValidationError("SCENE_STRUCTURE_MISMATCH")
            rules = tuple(rule for rule in rules if rule.target_scope == "scene")
        scenes = self._scenes(structure_id)
        metric_runs = self._metric_runs(document_id, text_id, structure_id, rules)
        measurements = self._measurements(metric_runs)
        scene_states, scene_warnings = self._scene_states(
            document_id, text_id, structure_id, scenes, rules, scene_id
        )
        links = self._character_links(document_id, rules)
        candidates, applicable, missing, warnings = self._candidates(
            document_id,
            rules,
            scenes,
            scene_id,
            scene_states,
            links,
            measurements,
            metric_runs,
            text_id,
            structure_id,
            cast(Callable[[int, int], None] | None, values.get("progress_callback")),
            cast(Callable[[], bool] | None, values.get("cancellation_probe")),
        )
        warnings = sorted(set((*scene_warnings, *warnings)))
        fingerprint = fingerprint_json(
            cast(
                JsonValue,
                {
                    "document_id": document_id,
                    "text_revision_id": text_id,
                    "structure_revision_id": structure_id,
                    "profile_version_id": version.id,
                    "scene_id": scene_id,
                    "basic_metric_run_id": metric_runs.get("basic"),
                    "semantic_metric_run_id": metric_runs.get("semantic"),
                    "scene_axis_state": scene_states,
                    "character_links": links,
                },
            )
        )
        return {
            "version_id": version.id,
            "basic_run_id": metric_runs.get("basic"),
            "semantic_run_id": metric_runs.get("semantic"),
            "fingerprint": fingerprint,
            "warnings": warnings,
            "enabled_count": len(rules),
            "applicable_count": applicable,
            "missing_count": missing,
            "findings": candidates,
        }

    def _metric_runs(
        self, document_id: int, text_id: int, structure_id: int, rules: tuple[Any, ...]
    ) -> dict[str, int | None]:
        groups = {METRIC_DEFINITIONS[rule.metric_name].group for rule in rules}
        resolver = CurrentRunResolver(self._connection)
        result: dict[str, int | None] = {}
        for group in sorted(groups):
            analyzer = _ANALYZER_BY_GROUP[group]
            run = resolver.resolve(document_id, text_id, structure_id, analyzer)
            result[f"{group}_run_id"] = None if run is None else run.id
            result[group] = None if run is None else run.id
        return result

    def _measurements(
        self, runs: dict[str, int | None]
    ) -> dict[tuple[str, str, int, str, int], float]:
        result: dict[tuple[str, str, int, str, int], float] = {}
        for group in ("basic", "semantic"):
            run_id = runs.get(group)
            if run_id is None:
                continue
            rows = self._connection.execute(
                "SELECT target_type, target_id, metric_name, metric_version, "
                "CASE WHEN value_int IS NULL THEN value_real ELSE value_int END "
                "FROM style_measurements WHERE analysis_run_id = ?",
                (run_id,),
            ).fetchall()
            for row in rows:
                key = (group, str(row[0]), int(row[1]), str(row[2]), int(row[3]))
                result[key] = float(row[4])
        return result

    def _scenes(self, structure_id: int) -> tuple[SceneRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, structure_revision_id, order_index, start_cp, end_cp "
            "FROM style_scenes WHERE structure_revision_id = ? "
            "ORDER BY order_index, id",
            (structure_id,),
        ).fetchall()
        return tuple(SceneRecord(*row) for row in rows)

    def _scene_states(
        self,
        document_id: int,
        text_id: int,
        structure_id: int,
        scenes: tuple[SceneRecord, ...],
        rules: tuple[Any, ...],
        requested_scene: int | None,
    ) -> tuple[list[JsonObject], list[str]]:
        axes = sorted(
            {
                axis
                for rule in rules
                if rule.target_scope == "scene"
                for axis in json.loads(rule.scope_selector_json)
            }
        )
        if not axes:
            return [], []
        run = CurrentRunResolver(self._connection).resolve(
            document_id, text_id, structure_id, "scene-semantic-classifier"
        )
        raw_by_scene: dict[int, dict[str, tuple[object, object, object]]] = {}
        if run is not None:
            rows = self._connection.execute(
                "SELECT annotation_type, value_json, confidence, start_cp, subject_id "
                "FROM style_annotations "
                "WHERE analysis_run_id = ? AND subject_type = 'scene'",
                (run.id,),
            ).fetchall()
            for row in rows:
                raw_by_scene.setdefault(int(row[4]), {})[str(row[0])] = (
                    row[1],
                    row[2],
                    row[3],
                )
        states: list[JsonObject] = []
        for scene in scenes:
            if requested_scene is not None and scene.id != requested_scene:
                continue
            effective = resolve_scene_semantics(
                self._connection,
                scene.id,
                None if run is None else run.id,
                raw_by_scene.get(scene.id, {}),
                structure_revision_id=structure_id,
            )
            for axis in axes:
                value = effective[f"scene.{axis}"]
                states.append(
                    {
                        "scene_id": scene.id,
                        "axis": axis,
                        "source": value.source,
                        "effective_value": cast(
                            JsonValue, scene_axis_values(axis, value.value)
                        ),
                    }
                )
        return states, []

    def _character_links(
        self, document_id: int, rules: tuple[Any, ...]
    ) -> list[JsonObject]:
        ids = sorted(
            {
                json.loads(rule.scope_selector_json).get("project_character_id")
                for rule in rules
                if rule.target_scope == "character"
            }
        )
        result: list[JsonObject] = []
        for project_character_id in ids:
            row = self._connection.execute(
                "SELECT style_entity_id FROM style_entity_character_links "
                "WHERE document_id = ? AND project_character_id = ?",
                (document_id, project_character_id),
            ).fetchone()
            entity_id = None if row is None else int(row[0])
            if entity_id is not None and not enabled_person(
                self._connection, entity_id
            ):
                entity_id = None
            result.append(
                {
                    "project_character_id": project_character_id,
                    "style_entity_id": entity_id,
                }
            )
        return result

    def _candidates(
        self,
        document_id: int,
        rules: tuple[Any, ...],
        scenes: tuple[SceneRecord, ...],
        requested_scene: int | None,
        states: list[JsonObject],
        links: list[JsonObject],
        measurements: dict[tuple[str, str, int, str, int], float],
        runs: dict[str, int | None],
        text_id: int,
        structure_id: int,
        progress_callback: Callable[[int, int], None] | None,
        cancellation_probe: Callable[[], bool] | None,
    ) -> tuple[list[tuple[object, ...]], int, int, list[str]]:
        state_map: dict[tuple[int, str], JsonObject] = {}
        for item in states:
            scene_value = item.get("scene_id")
            axis_value = item.get("axis")
            if isinstance(scene_value, int) and isinstance(axis_value, str):
                state_map[(scene_value, axis_value)] = item
        link_map: dict[int, object] = {}
        for item in links:
            project_value = item.get("project_character_id")
            if isinstance(project_value, int):
                link_map[project_value] = item.get("style_entity_id")
        candidates: list[_Candidate] = []
        applicable = 0
        missing = 0
        warnings: list[str] = []
        targets: list[tuple[str, int]] = [("document", document_id)]
        if requested_scene is None:
            targets.extend(("scene", scene.id) for scene in scenes)
        else:
            targets = [("scene", requested_scene)]
        for rule in rules:
            selector = json.loads(rule.scope_selector_json)
            if rule.target_scope == "character":
                project_value = selector.get("project_character_id")
                if not isinstance(project_value, int):
                    continue
                project_id = project_value
                entity_id = link_map.get(project_id)
                if isinstance(entity_id, int):
                    candidates.append(_Candidate(rule, "character", entity_id, 0))
                continue
            rule_targets = [
                target for target in targets if target[0] == rule.target_scope
            ]
            for target_type, target_id in rule_targets:
                if target_type == "scene":
                    unknown = [
                        axis
                        for axis in selector
                        if state_map.get((target_id, axis), {}).get("effective_value")
                        is None
                    ]
                    if unknown:
                        applicable += 1
                        missing += 1
                        warnings.extend(
                            f"SELECTOR_UNAVAILABLE:{axis}" for axis in unknown
                        )
                        continue
                    matches = True
                    for axis in selector:
                        effective_value = state_map[(target_id, axis)].get(
                            "effective_value"
                        )
                        if not isinstance(effective_value, list) or not all(
                            isinstance(item, str) for item in effective_value
                        ):
                            matches = False
                            break
                        if not set(selector[axis]) & set(effective_value):
                            matches = False
                            break
                    if not matches:
                        continue
                    specificity = len(selector)
                else:
                    specificity = 0
                candidates.append(_Candidate(rule, target_type, target_id, specificity))
        selected: list[_Candidate] = []
        by_target_metric: dict[tuple[str, int, str], list[_Candidate]] = {}
        for candidate in candidates:
            key = (
                candidate.target_type,
                candidate.target_id,
                candidate.rule.metric_name,
            )
            by_target_metric.setdefault(key, []).append(candidate)
        for candidate_group in by_target_metric.values():
            maximum = max(item.specificity for item in candidate_group)
            selected.extend(
                item for item in candidate_group if item.specificity == maximum
            )
        findings: list[tuple[object, ...]] = []
        total = len(selected)
        if progress_callback is not None:
            progress_callback(0, total)
        for candidate in selected:
            if cancellation_probe is not None and cancellation_probe():
                raise AnalysisCancelledError()
            applicable += 1
            rule = candidate.rule
            definition = METRIC_DEFINITIONS[rule.metric_name]
            metric_group = definition.group
            measurement_key = (
                metric_group,
                candidate.target_type,
                candidate.target_id,
                rule.metric_name,
                rule.metric_version,
            )
            observed = measurements.get(measurement_key)
            if observed is None:
                missing += 1
                warnings.append(f"METRIC_UNAVAILABLE:{rule.metric_name}")
                if progress_callback is not None:
                    progress_callback(applicable, total)
                continue
            deviation, explanation = _deviation(
                observed,
                float(rule.min_value),
                float(rule.max_value),
                definition.zero_width_tolerance,
            )
            if deviation == 0:
                if progress_callback is not None:
                    progress_callback(applicable, total)
                continue
            severity = (
                "info"
                if deviation <= 0.25
                else "warning"
                if deviation <= 0.75
                else "strong_warning"
            )
            evidence = build_lint_evidence(
                self._connection,
                metric_name=rule.metric_name,
                target_type=candidate.target_type,
                target_id=candidate.target_id,
                text_revision_id=text_id,
                structure_revision_id=structure_id,
            )
            findings.append(
                (
                    rule.id,
                    candidate.target_type,
                    candidate.target_id,
                    rule.metric_name,
                    observed,
                    float(rule.min_value),
                    float(rule.max_value),
                    None
                    if rule.preferred_value is None
                    else float(rule.preferred_value),
                    deviation,
                    severity,
                    deviation * float(rule.weight),
                    explanation,
                    json_text(evidence),
                )
            )
            if progress_callback is not None:
                progress_callback(applicable, total)
        return findings, applicable, missing, sorted(set(warnings))

    def _profile_version_no(self, version_id: int) -> int:
        row = self._connection.execute(
            "SELECT version_no FROM style_profile_versions WHERE id = ?", (version_id,)
        ).fetchone()
        if row is None:
            raise ValidationError("PROFILE_VERSION_NOT_FOUND")
        return int(row[0])


def _positive(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(code)
    return value


def _deviation(
    observed: float, minimum: float, maximum: float, tolerance: float
) -> tuple[float, str]:
    if minimum <= observed <= maximum:
        return 0.0, "within_range"
    if minimum == maximum:
        return abs(
            observed - minimum
        ) / tolerance, "below_range" if observed < minimum else "above_range"
    if observed < minimum:
        return (minimum - observed) / (maximum - minimum), "below_range"
    return (observed - maximum) / (maximum - minimum), "above_range"
