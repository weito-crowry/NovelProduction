from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import cast

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.analysis_runtime import AnalysisRuntime
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.metrics import BASIC_METRIC_DEFINITIONS
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.runtime_models import (
    AnalysisRunRecord,
    DependencyRunExpectation,
)
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID
from novel_core.style_analysis.semantic_models import AnnotationRecord
from novel_core.style_analysis.semantic_repository import SemanticRepository
from novel_core.style_analysis.source_models import (
    ReferenceEpisodeRecord,
    ReferenceWorkRecord,
)
from novel_core.style_analysis.source_repository import StyleSourceRepository

_SA_D_ANALYZERS = (
    "entity-mention-extractor",
    "entity-resolver",
    "speaker-attribution",
    "term-candidate-extractor",
    "term-resolver",
    "term-explanation-detector",
    "scene-semantic-classifier",
    "block-semantic-classifier",
    "pov-classifier",
)

_PROMPT_IDS = {
    "entity-mention-extractor": "style.entity_mentions",
    "entity-resolver": "style.entity_resolution",
    "speaker-attribution": "style.speaker_attribution",
    "term-candidate-extractor": "style.term_candidates",
    "term-resolver": "style.term_resolution",
    "term-explanation-detector": "style.term_explanation",
    "scene-semantic-classifier": "style.scene_semantics",
    "block-semantic-classifier": "style.block_semantic",
    "pov-classifier": "style.pov",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class StyleAnalysisCatalogService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = StyleSourceRepository(connection)
        self._connection = connection
        self._runs = AnalysisRunRepository(connection)
        self._annotations = SemanticRepository(connection)

    def list_reference_works(self) -> tuple[ReferenceWorkRecord, ...]:
        return self._repository.list_reference_works()

    def get_reference_work(self, work_id: int) -> ReferenceWorkRecord | None:
        return self._repository.get_reference_work(work_id)

    def list_reference_episodes(
        self, work_id: int
    ) -> tuple[ReferenceEpisodeRecord, ...]:
        return self._repository.list_reference_episodes(work_id)

    def get_reference_episode(self, episode_id: int) -> ReferenceEpisodeRecord | None:
        return self._repository.get_reference_episode(episode_id)

    def purge_reference_work(self, work_id: int) -> bool:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            deleted = self._repository.purge_reference_work(work_id)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return deleted

    def list_analysis_runs(
        self, document_id: int | None = None
    ) -> tuple[AnalysisRunRecord, ...]:
        if document_id is None:
            rows = self._connection.execute(
                "SELECT id FROM style_analysis_runs ORDER BY created_at DESC, id DESC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT id FROM style_analysis_runs WHERE document_id = ? "
                "ORDER BY created_at DESC, id DESC",
                (document_id,),
            ).fetchall()
        return tuple(
            run for row in rows if (run := self._runs.get_run(int(row[0]))) is not None
        )

    def get_analysis_run(self, run_id: int) -> AnalysisRunRecord | None:
        return self._runs.get_run(run_id)

    def list_run_outputs(self, run_id: int) -> tuple[dict[str, object], ...]:
        outputs = [
            self._annotation_response(annotation)
            for annotation in self._annotations.list_for_run(run_id)
        ]
        run = self._runs.get_run(run_id)
        if run is not None and run.analyzer_id == "entity-mention-extractor":
            outputs.extend(self._mentions_for_runs((run_id,)))
        return tuple(outputs)

    def list_run_measurements(self, run_id: int) -> tuple[dict[str, object], ...]:
        # Measurement persistence is introduced by the later metrics phase.
        return ()

    def get_semantics(
        self, document_id: int, structure_revision_id: int
    ) -> dict[str, object]:
        text_row = self._connection.execute(
            "SELECT sr.text_revision_id "
            "FROM style_structure_revisions sr "
            "JOIN style_text_revisions tr ON tr.id = sr.text_revision_id "
            "WHERE sr.id = ? AND tr.document_id = ?",
            (structure_revision_id, document_id),
        ).fetchone()
        if text_row is None:
            raise ValueError("STRUCTURE_NOT_FOUND")
        selected = self._select_runs(
            document_id,
            int(text_row[0]),
            structure_revision_id,
            _SA_D_ANALYZERS,
        )
        run_ids = [run.id for run in selected]
        outputs = [
            output for run_id in run_ids for output in self.list_run_outputs(run_id)
        ]
        entities = self._entities_for_document(document_id)
        terms = self._terms_for_document(document_id)
        mentions = self._mentions_for_runs(
            tuple(
                run.id
                for run in selected
                if run.analyzer_id == "entity-mention-extractor"
            )
        )
        term_mentions = self._term_mentions_for_runs(
            tuple(run.id for run in selected if run.analyzer_id == "term-resolver")
        )
        by_type = {
            "entities": entities,
            "mentions": mentions,
            "speakers": [
                output
                for output in outputs
                if output.get("annotation_type") == "speaker"
            ],
            "terms": terms,
            "term_mentions": term_mentions,
            "explanations": [
                output
                for output in outputs
                if output.get("annotation_type") == "term_explanation"
            ],
            "scenes": [
                output for output in outputs if output.get("subject_type") == "scene"
            ],
            "blocks": [
                output for output in outputs if output.get("subject_type") == "block"
            ],
        }
        by_type["scene_axes"] = by_type["scenes"]
        by_type["pov"] = [
            output for output in outputs if output.get("annotation_type") == "scene.pov"
        ]
        current_row = self._connection.execute(
            "SELECT current_text_revision_id, current_structure_revision_id "
            "FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        status = self.analysis_status(
            document_id,
            None if current_row is None else current_row[0],
            None if current_row is None else current_row[1],
        )
        raw = [*outputs]
        effective = self._effective_outputs(
            outputs,
            mentions=mentions,
            structure_revision_id=structure_revision_id,
        )
        return {
            "structure_revision_id": structure_revision_id,
            "analysis_run_ids": run_ids,
            "outputs": outputs,
            **by_type,
            "raw": raw,
            "effective": effective,
            "analysis_status": status,
        }

    def _select_runs(
        self,
        document_id: int,
        text_revision_id: int,
        structure_revision_id: int,
        analyzer_ids: tuple[str, ...],
    ) -> tuple[AnalysisRunRecord, ...]:
        orchestrator = DocumentAnalysisOrchestrator(
            self._connection,
            model_client=None,
            model_provider=None,
            model_id=None,
        )
        runtime = AnalysisRuntime(self._runs)
        current: dict[str, AnalysisRunRecord] = {}
        for analyzer_id in analyzer_ids:
            definition = ANALYZERS_BY_ID.get(analyzer_id)
            if definition is None:
                continue
            dependencies: list[tuple[str, int]] = []
            expectations: list[DependencyRunExpectation] = []
            dependencies_ready = True
            for dependency in definition.dependencies:
                selected_dependency = current.get(dependency.analyzer_id)
                if selected_dependency is None or (
                    dependency.mode == "complete"
                    and selected_dependency.status != "succeeded"
                ):
                    dependencies_ready = False
                    break
                dependencies.append((dependency.analyzer_id, selected_dependency.id))
                expectations.append(
                    DependencyRunExpectation(
                        analyzer_id=dependency.analyzer_id,
                        run_id=selected_dependency.id,
                        config_json=selected_dependency.config_json,
                        state_fingerprint=selected_dependency.state_fingerprint,
                        policy_input_fingerprint=(
                            selected_dependency.policy_input_fingerprint
                        ),
                        prompt_id=selected_dependency.prompt_id,
                        prompt_version=selected_dependency.prompt_version,
                    )
                )
            if not dependencies_ready:
                continue
            config_json = _canonical_json(self._config_for_analyzer(analyzer_id))
            state = self._state_for_analyzer(
                orchestrator,
                analyzer_id,
                document_id,
                structure_revision_id,
                current,
            )
            state_fingerprint = None if state is None else fingerprint_json(state)
            policy_input_fingerprint = (
                fingerprint_json(
                    cast(
                        JsonValue,
                        orchestrator.policy.input_values(definition.policy_inputs),
                    )
                )
                if definition.policy_inputs
                else None
            )
            prompt_id = _PROMPT_IDS.get(analyzer_id)
            prompt_version = None
            if prompt_id is not None:
                prompt_version = get_prompt(prompt_id).version
            selected = runtime.resolve_current_run(
                document_id=document_id,
                analyzer_id=analyzer_id,
                text_revision_id=text_revision_id,
                structure_revision_id=structure_revision_id,
                analyzer_version=definition.version,
                config_json=config_json,
                state_fingerprint=state_fingerprint,
                policy_input_fingerprint=policy_input_fingerprint,
                dependency_runs=tuple(dependencies),
                dependency_expectations=tuple(expectations),
                prompt_id=prompt_id,
                prompt_version=prompt_version,
            )
            if selected is not None:
                current[analyzer_id] = selected
        return tuple(
            current[analyzer_id]
            for analyzer_id in analyzer_ids
            if analyzer_id in current
        )

    @staticmethod
    def _config_for_analyzer(analyzer_id: str) -> JsonValue:
        if analyzer_id == "scene-semantic-classifier":
            return {"scene_taxonomy_version": 1}
        if analyzer_id == "block-semantic-classifier":
            return {"block_semantic_taxonomy_version": 1}
        if analyzer_id == "pov-classifier":
            return {"pov_taxonomy_version": 1}
        return {}

    @staticmethod
    def _state_for_analyzer(
        orchestrator: DocumentAnalysisOrchestrator,
        analyzer_id: str,
        document_id: int,
        structure_revision_id: int,
        current: dict[str, AnalysisRunRecord],
    ) -> JsonValue | None:
        if analyzer_id == "entity-resolver":
            return cast(
                JsonValue,
                {
                    "scope": orchestrator.entities._scope(document_id),
                    "entity_registry_state": orchestrator._entity_registry_state(
                        document_id
                    ),
                },
            )
        if analyzer_id == "term-resolver":
            return cast(
                JsonValue,
                {
                    "scope": orchestrator.terms._scope(document_id),
                    "term_registry_state": orchestrator._term_registry_state(
                        document_id
                    ),
                },
            )
        if analyzer_id in {"speaker-attribution", "pov-classifier"}:
            entity_run = current.get("entity-resolver")
            if entity_run is None:
                return None
            return cast(
                JsonValue,
                {
                    "mention_resolution": orchestrator._mention_resolution_state(
                        document_id, structure_revision_id, entity_run.id
                    )
                },
            )
        return None

    def _entities_for_document(self, document_id: int) -> list[dict[str, object]]:
        row = self._connection.execute(
            "SELECT reference_episode_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return []
        if row[0] is None:
            predicate, value = "e.document_id = ?", document_id
        else:
            work = self._connection.execute(
                "SELECT reference_work_id FROM style_reference_episodes WHERE id = ?",
                (row[0],),
            ).fetchone()
            if work is None:
                return []
            predicate, value = "e.reference_work_id = ?", work[0]
        rows = self._connection.execute(
            "SELECT e.id, e.entity_type, e.canonical_name, e.origin "
            f"FROM style_entities e WHERE {predicate} ORDER BY e.id",
            (value,),
        ).fetchall()
        return [
            {
                "id": row[0],
                "entity_type": row[1],
                "canonical_name": row[2],
                "origin": row[3],
            }
            for row in rows
        ]

    def _terms_for_document(self, document_id: int) -> list[dict[str, object]]:
        row = self._connection.execute(
            "SELECT reference_episode_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return []
        if row[0] is None:
            predicate, value = "t.document_id = ?", document_id
        else:
            work = self._connection.execute(
                "SELECT reference_work_id FROM style_reference_episodes WHERE id = ?",
                (row[0],),
            ).fetchone()
            if work is None:
                return []
            predicate, value = "t.reference_work_id = ?", work[0]
        rows = self._connection.execute(
            "SELECT t.id, t.canonical_label, t.term_type, t.origin "
            f"FROM style_terms t WHERE {predicate} ORDER BY t.id",
            (value,),
        ).fetchall()
        return [
            {
                "id": row[0],
                "canonical_label": row[1],
                "term_type": row[2],
                "origin": row[3],
            }
            for row in rows
        ]

    def _term_mentions_for_runs(
        self, run_ids: tuple[int, ...]
    ) -> list[dict[str, object]]:
        if not run_ids:
            return []
        placeholders = ",".join("?" for _ in run_ids)
        rows = self._connection.execute(
            "SELECT id, term_id, structure_revision_id, scene_id, block_id, "
            "start_cp, end_cp, surface, analysis_run_id "
            "FROM style_term_mentions "
            f"WHERE analysis_run_id IN ({placeholders}) ORDER BY id",
            run_ids,
        ).fetchall()
        return [
            {
                "id": row[0],
                "term_id": row[1],
                "structure_revision_id": row[2],
                "scene_id": row[3],
                "block_id": row[4],
                "start_cp": row[5],
                "end_cp": row[6],
                "surface": row[7],
                "analysis_run_id": row[8],
            }
            for row in rows
        ]

    def _mentions_for_runs(self, run_ids: tuple[int, ...]) -> list[dict[str, object]]:
        if not run_ids:
            return []
        placeholders = ",".join("?" for _ in run_ids)
        rows = self._connection.execute(
            "SELECT id, structure_revision_id, scene_id, block_id, start_cp, end_cp, "
            "surface, mention_type, entity_type_candidate, "
            "canonical_name_candidate, confidence, analysis_run_id "
            "FROM style_mentions "
            f"WHERE analysis_run_id IN ({placeholders}) ORDER BY id",
            run_ids,
        ).fetchall()
        return [
            {
                "id": row[0],
                "structure_revision_id": row[1],
                "scene_id": row[2],
                "block_id": row[3],
                "start_cp": row[4],
                "end_cp": row[5],
                "surface": row[6],
                "mention_type": row[7],
                "entity_type_candidate": row[8],
                "canonical_name_candidate": row[9],
                "confidence": row[10],
                "analysis_run_id": row[11],
            }
            for row in rows
        ]

    def _effective_outputs(
        self,
        outputs: Sequence[dict[str, object]],
        *,
        mentions: Sequence[dict[str, object]] = (),
        structure_revision_id: int | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        effective: dict[str, list[dict[str, object]]] = {
            "mentions": [dict(mention, source="inferred") for mention in mentions],
            "speakers": [],
            "explanations": [],
            "scenes": [],
            "scene_axes": [],
            "pov": [],
            "blocks": [],
        }
        policy = DocumentAnalysisOrchestrator(
            self._connection,
            model_client=None,
        ).policy
        for output in outputs:
            item = dict(output)
            annotation_type = output.get("annotation_type")
            confidence = output.get("confidence")
            confidence_value = (
                float(confidence)
                if isinstance(confidence, (int, float))
                and not isinstance(confidence, bool)
                else None
            )
            if annotation_type == "speaker":
                value = self._mapping_value(output)
                if (
                    value.get("reason_code") == "turn_taking"
                    or confidence_value is None
                    or confidence_value < policy.speaker_effective
                ):
                    value["speaker_entity_id"] = None
                    item["source"] = "unknown"
                else:
                    item["source"] = "inferred"
                item["value"] = value
                effective["speakers"].append(item)
                continue
            if annotation_type in {
                "scene.function",
                "scene.tone",
            }:
                value = self._mapping_value(output)
                labels = value.get("labels")
                accepted: list[object] = []
                if isinstance(labels, list):
                    for label in labels:
                        if not isinstance(label, dict):
                            continue
                        label_name = label.get("label")
                        label_confidence = label.get("confidence", confidence_value)
                        if label_name == "unclear":
                            continue
                        if (
                            isinstance(label_confidence, (int, float))
                            and not isinstance(label_confidence, bool)
                            and label_confidence >= policy.scene_label_effective
                        ):
                            accepted.append(dict(label))
                value["labels"] = accepted or [
                    {"label": "unclear", "confidence": confidence_value}
                ]
                item["value"] = value
                item["source"] = "inferred"
                effective["scenes"].append(item)
                effective["scene_axes"].append(item)
                continue
            if annotation_type in {
                "scene.pace",
                "scene.information_load",
                "scene.interaction",
            }:
                value = self._mapping_value(output)
                if (
                    confidence_value is None
                    or confidence_value < policy.scene_label_effective
                ):
                    value["label"] = "unclear"
                item["value"] = value
                item["source"] = "inferred"
                effective["scenes"].append(item)
                effective["scene_axes"].append(item)
                continue
            if annotation_type == "scene.pov":
                value = self._mapping_value(output)
                if confidence_value is None or confidence_value < policy.pov_effective:
                    value["pov_mode"] = "unclear"
                    value["pov_entity_id"] = None
                item["value"] = value
                item["source"] = "inferred"
                effective["scenes"].append(item)
                effective["pov"].append(item)
                continue
            if annotation_type == "block.semantic_primary":
                value = self._mapping_value(output)
                if (
                    confidence_value is None
                    or confidence_value < policy.block_semantic_effective
                ):
                    value["label"] = "unclear"
                item["value"] = value
                item["source"] = "inferred"
                effective["blocks"].append(item)
                continue
            if annotation_type == "term_explanation":
                if (
                    confidence_value is None
                    or confidence_value < policy.term_explanation_effective
                ):
                    item["value"] = None
                item["source"] = "inferred"
                effective["explanations"].append(item)

        if structure_revision_id is not None:
            self._append_unknown_effective_values(effective, structure_revision_id)
        return effective

    @staticmethod
    def _mapping_value(output: dict[str, object]) -> dict[str, object]:
        value = output.get("value")
        return dict(cast(dict[str, object], value)) if isinstance(value, dict) else {}

    def _append_unknown_effective_values(
        self,
        effective: dict[str, list[dict[str, object]]],
        structure_revision_id: int,
    ) -> None:
        scenes = self._connection.execute(
            "SELECT id FROM style_scenes WHERE structure_revision_id = ? ORDER BY id",
            (structure_revision_id,),
        ).fetchall()
        scene_axes = (
            "scene.function",
            "scene.tone",
            "scene.pace",
            "scene.information_load",
            "scene.interaction",
        )
        existing_scene_axes = {
            (item.get("annotation_type"), item.get("subject_id"))
            for item in effective["scene_axes"]
        }
        for (scene_id,) in scenes:
            for annotation_type in scene_axes:
                if (annotation_type, scene_id) in existing_scene_axes:
                    continue
                unknown = {
                    "annotation_type": annotation_type,
                    "subject_type": "scene",
                    "subject_id": scene_id,
                    "value": None,
                    "confidence": None,
                    "analysis_run_id": None,
                    "source": "unknown",
                }
                effective["scenes"].append(unknown)
                effective["scene_axes"].append(unknown)
            if not any(item.get("subject_id") == scene_id for item in effective["pov"]):
                effective["pov"].append(
                    {
                        "annotation_type": "scene.pov",
                        "subject_type": "scene",
                        "subject_id": scene_id,
                        "value": None,
                        "confidence": None,
                        "analysis_run_id": None,
                        "source": "unknown",
                    }
                )
        blocks = self._connection.execute(
            "SELECT id, block_type FROM style_blocks "
            "WHERE structure_revision_id = ? ORDER BY id",
            (structure_revision_id,),
        ).fetchall()
        existing_blocks = {item.get("subject_id") for item in effective["blocks"]}
        for block_id, block_type in blocks:
            if block_type == "narration" and block_id not in existing_blocks:
                effective["blocks"].append(
                    {
                        "annotation_type": "block.semantic_primary",
                        "subject_type": "block",
                        "subject_id": block_id,
                        "value": None,
                        "confidence": None,
                        "analysis_run_id": None,
                        "source": "unknown",
                    }
                )

    def analysis_status(
        self,
        document_id: int,
        text_revision_id: int | None,
        structure_revision_id: int | None,
    ) -> dict[str, object]:
        runs = self.list_analysis_runs(document_id)
        basic_history = tuple(
            run for run in runs if run.analyzer_id == "style-metrics-basic"
        )
        basic_runs = (
            self._select_runs(
                document_id,
                text_revision_id,
                structure_revision_id,
                ("style-metrics-basic",),
            )
            if text_revision_id is not None and structure_revision_id is not None
            else ()
        )
        basic_run = basic_runs[0] if basic_runs else None
        basic_current = (
            basic_run is not None
            and basic_run.status == "succeeded"
            and self._run_has_current_inputs(basic_run, document_id)
        )
        if basic_current:
            basic = {"state": "current", "reasons": []}
        elif any(run.status == "succeeded" for run in basic_history):
            basic = {"state": "stale", "reasons": ["CURRENT_REVISION_CHANGED"]}
        else:
            basic = {"state": "not_analyzed", "reasons": []}

        semantic_ids = {
            "entity-mention-extractor",
            "entity-resolver",
            "speaker-attribution",
            "term-candidate-extractor",
            "term-resolver",
            "term-explanation-detector",
            "scene-semantic-classifier",
            "block-semantic-classifier",
            "pov-classifier",
        }
        semantic_history = tuple(run for run in runs if run.analyzer_id in semantic_ids)
        current_semantic = (
            self._select_runs(
                document_id,
                text_revision_id,
                structure_revision_id,
                _SA_D_ANALYZERS,
            )
            if text_revision_id is not None and structure_revision_id is not None
            else ()
        )
        current_by_analyzer = {run.analyzer_id: run for run in current_semantic}
        state_current = self._semantic_runs_have_current_inputs(
            document_id, structure_revision_id, current_by_analyzer
        )
        resolution_state_changed = self._semantic_resolution_state_changed(
            document_id,
            text_revision_id,
            structure_revision_id,
            semantic_history,
            current_by_analyzer,
        )
        if (
            semantic_ids.issubset(current_by_analyzer)
            and all(run.status == "succeeded" for run in current_by_analyzer.values())
            and state_current
        ):
            semantic = {"state": "current", "reasons": []}
        elif current_by_analyzer and (not state_current or resolution_state_changed):
            semantic = {"state": "stale", "reasons": ["CURRENT_RESOLUTION_CHANGED"]}
        elif any(
            run.status in {"succeeded", "partial"} for run in current_semantic
        ) and (
            any(run.status in {"partial", "failed"} for run in current_semantic)
            or len(current_by_analyzer) < len(semantic_ids)
        ):
            semantic = {"state": "partial", "reasons": ["SEMANTIC_BRANCH_PARTIAL"]}
        elif any(run.status in {"succeeded", "partial"} for run in semantic_history):
            semantic = {"state": "stale", "reasons": ["CURRENT_REVISION_CHANGED"]}
        else:
            semantic = {"state": "not_analyzed", "reasons": []}
        return {"basic": basic, "semantic": semantic}

    def _semantic_resolution_state_changed(
        self,
        document_id: int,
        text_revision_id: int | None,
        structure_revision_id: int | None,
        history: Sequence[AnalysisRunRecord],
        current: dict[str, AnalysisRunRecord],
    ) -> bool:
        if text_revision_id is None or structure_revision_id is None:
            return False
        orchestrator = DocumentAnalysisOrchestrator(
            self._connection,
            model_client=None,
            model_provider=None,
            model_id=None,
        )
        for analyzer_id in ("entity-resolver", "term-resolver"):
            if analyzer_id in current:
                continue
            state = self._state_for_analyzer(
                orchestrator,
                analyzer_id,
                document_id,
                structure_revision_id,
                {},
            )
            expected = None if state is None else fingerprint_json(state)
            for run in history:
                if (
                    run.analyzer_id == analyzer_id
                    and run.text_revision_id == text_revision_id
                    and run.structure_revision_id == structure_revision_id
                    and run.status in {"succeeded", "partial"}
                    and run.state_fingerprint != expected
                ):
                    return True
        return False

    def _semantic_runs_have_current_inputs(
        self,
        document_id: int,
        structure_revision_id: int | None,
        runs: dict[str, AnalysisRunRecord],
    ) -> bool:
        if structure_revision_id is None:
            return False
        orchestrator = DocumentAnalysisOrchestrator(
            self._connection,
            model_client=None,
            model_provider=None,
            model_id=None,
        )
        entity_run = runs.get("entity-resolver")
        for run in runs.values():
            expected_config: object = {}
            if run.analyzer_id == "scene-semantic-classifier":
                expected_config = {"scene_taxonomy_version": 1}
            elif run.analyzer_id == "block-semantic-classifier":
                expected_config = {"block_semantic_taxonomy_version": 1}
            elif run.analyzer_id == "pov-classifier":
                expected_config = {"pov_taxonomy_version": 1}
            if run.config_json != _canonical_json(expected_config):
                return False
            if run.analyzer_id == "entity-resolver":
                expected_state = {
                    "scope": orchestrator.entities._scope(document_id),
                    "entity_registry_state": orchestrator._entity_registry_state(
                        document_id
                    ),
                }
            elif run.analyzer_id == "term-resolver":
                expected_state = {
                    "scope": orchestrator.terms._scope(document_id),
                    "term_registry_state": orchestrator._term_registry_state(
                        document_id
                    ),
                }
            elif run.analyzer_id in {"speaker-attribution", "pov-classifier"}:
                if entity_run is None:
                    return False
                expected_state = {
                    "mention_resolution": orchestrator._mention_resolution_state(
                        document_id, structure_revision_id, entity_run.id
                    )
                }
            else:
                expected_state = None
            if expected_state is not None:
                if run.state_fingerprint != fingerprint_json(
                    cast(JsonValue, expected_state)
                ):
                    return False
        return True

    @staticmethod
    def _run_has_current_inputs(run: AnalysisRunRecord, document_id: int) -> bool:
        if run.analyzer_id != "style-metrics-basic":
            return True
        expected = {
            "metric_versions": {
                name: definition.version
                for name, definition in sorted(BASIC_METRIC_DEFINITIONS.items())
            }
        }
        return run.config_json == _canonical_json(expected)

    def list_annotations(self, document_id: int) -> tuple[dict[str, object], ...]:
        rows = self._connection.execute(
            "SELECT a.id, a.annotation_type, a.subject_type, a.subject_id, "
            "a.value_json, a.confidence, a.analysis_run_id, a.start_cp, a.end_cp, "
            "a.created_at FROM style_annotations a "
            "JOIN style_analysis_runs r ON r.id = a.analysis_run_id "
            "WHERE r.document_id = ? ORDER BY a.id",
            (document_id,),
        ).fetchall()
        return tuple(
            {
                "id": row[0],
                "annotation_type": row[1],
                "subject_type": row[2],
                "subject_id": row[3],
                "value": json.loads(row[4]),
                "confidence": row[5],
                "analysis_run_id": row[6],
                "start_cp": row[7],
                "end_cp": row[8],
                "created_at": row[9],
            }
            for row in rows
        )

    def list_boundary_proposals(
        self,
        document_id: int,
        *,
        min_confidence: float = 0.60,
        include_below_threshold: bool = False,
    ) -> tuple[dict[str, object], ...]:
        confidence_clause = "" if include_below_threshold else "AND a.confidence >= ? "
        parameters: tuple[object, ...] = (document_id,)
        if not include_below_threshold:
            parameters += (min_confidence,)
        rows = self._connection.execute(
            "SELECT a.id, a.subject_id, a.value_json, a.confidence, "
            "a.analysis_run_id "
            "FROM style_annotations a "
            "JOIN style_analysis_runs r ON r.id = a.analysis_run_id "
            "WHERE r.document_id = ? "
            "AND a.annotation_type = 'scene_boundary_candidate' "
            f"{confidence_clause}ORDER BY a.id",
            parameters,
        ).fetchall()
        return tuple(
            {
                "id": row[0],
                "subject_type": "block",
                "subject_id": row[1],
                "after_block_id": row[1],
                "value": json.loads(row[2]),
                "confidence": row[3],
                "analysis_run_id": row[4],
            }
            for row in rows
        )

    @staticmethod
    def _annotation_response(annotation: AnnotationRecord) -> dict[str, object]:
        return {
            "id": annotation.id,
            "annotation_type": annotation.annotation_type,
            "subject_type": annotation.subject_type,
            "subject_id": annotation.subject_id,
            "value": json.loads(annotation.value_json),
            "confidence": annotation.confidence,
            "analysis_run_id": annotation.analysis_run_id,
            "start_cp": annotation.start_cp,
            "end_cp": annotation.end_cp,
            "created_at": annotation.created_at,
        }
