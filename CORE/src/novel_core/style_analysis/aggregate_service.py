from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.aggregate_calculations import (
    _STATISTICS,
    _canonical_filter_json,
    _effective_axis_values,
    _filter_state_fingerprint,
    _input_fingerprint,
    _metric_version,
    _parse_filter,
    _statistic_value,
    _Target,
)
from novel_core.style_analysis.aggregate_repository import (
    AggregateRepository,
    MeasurementRepository,
    json_object,
)
from novel_core.style_analysis.corpus_models import (
    AggregateRecord,
    AggregateSpec,
    ContainerType,
    MeasurementTargetType,
)
from novel_core.style_analysis.corpus_repository import CorpusRepository
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.fingerprints import JsonValue
from novel_core.style_analysis.metrics import METRIC_DEFINITIONS


@dataclass(frozen=True, slots=True)
class AggregatePolicy:
    version: int = 1


@dataclass(frozen=True, slots=True)
class AggregateRecomputeResult:
    aggregates: tuple[AggregateRecord, ...]
    warnings: tuple[str, ...]


class AggregateService:
    def __init__(
        self, connection: sqlite3.Connection, *, policy: AggregatePolicy | None = None
    ) -> None:
        self._connection = connection
        self.policy = policy or AggregatePolicy()
        self.corpora = CorpusRepository(connection)
        self.measurements = MeasurementRepository(connection)
        self.aggregates = AggregateRepository(connection)
        self._current_runs = CurrentRunResolver(connection)

    def recompute(
        self,
        specs: tuple[AggregateSpec, ...],
        metric_names: tuple[str, ...] = (),
    ) -> AggregateRecomputeResult:
        self._current_runs.clear()
        if not metric_names:
            for spec in specs:
                if _metric_version(spec.metric_name) != spec.metric_version:
                    raise ValidationError("METRIC_NOT_FOUND")
        expanded = tuple(
            AggregateSpec(
                spec.container_type,
                spec.container_id,
                spec.measurement_target_type,
                _canonical_filter_json(spec.filter_json, spec.measurement_target_type),
                metric_name,
                _metric_version(metric_name),
            )
            for spec in specs
            for metric_name in (metric_names or (spec.metric_name,))
        )
        if not expanded:
            return AggregateRecomputeResult((), ())
        savepoint = "aggregate_recompute"
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            else:
                self._connection.execute(f"SAVEPOINT {savepoint}")
            result_rows: list[AggregateRecord] = []
            warnings: list[str] = []
            for spec in expanded:
                computed = self._compute(spec)
                warnings.extend(computed[1])
                values, computed_warnings, source_episode_ids = computed
                if not any(target.value is not None for target in values):
                    continue
                for statistic in _STATISTICS:
                    aggregate = self.aggregates.insert(
                        container_type=spec.container_type,
                        container_id=spec.container_id,
                        measurement_target_type=spec.measurement_target_type,
                        filter_json=spec.filter_json,
                        metric_name=spec.metric_name,
                        metric_version=spec.metric_version,
                        statistic=statistic,
                        aggregate_policy_version=self.policy.version,
                        value_real=_statistic_value(statistic, values),
                        source_measurement_count=sum(
                            target.measurement_id is not None for target in values
                        ),
                        sample_count=sum(target.sample_count for target in values),
                        work_count=len(
                            {
                                target.work_id
                                for target in values
                                if target.measurement_id is not None
                            }
                        ),
                        skipped_target_count=sum(
                            target.filter_result == "unknown" for target in values
                        )
                        + sum(
                            1
                            for target in values
                            if target.measurement_id is None
                            and target.filter_result == "match"
                        ),
                        filter_state_fingerprint=_filter_state_fingerprint(values),
                        input_fingerprint=_input_fingerprint(
                            self.policy.version,
                            spec,
                            values,
                            statistic,
                            source_episode_ids=source_episode_ids,
                        ),
                        warning_json=json_object(sorted(set(computed_warnings))),
                    )
                    self.aggregates.link_measurements(
                        aggregate.id,
                        tuple(
                            target.measurement_id
                            for target in values
                            if target.measurement_id is not None
                        ),
                    )
                    result_rows.append(aggregate)
            if owns_transaction:
                self._connection.commit()
            else:
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            return AggregateRecomputeResult(
                tuple(result_rows), tuple(sorted(set(warnings)))
            )
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            else:
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise

    def list_with_staleness(
        self,
        *,
        container_type: ContainerType,
        container_id: int,
        measurement_target_type: MeasurementTargetType | None = None,
    ) -> tuple[AggregateRecord, ...]:
        result: list[AggregateRecord] = []
        for aggregate in self.aggregates.list(
            container_type=container_type,
            container_id=container_id,
            measurement_target_type=measurement_target_type,
        ):
            spec = AggregateSpec(
                aggregate.container_type,
                aggregate.container_id,
                aggregate.measurement_target_type,
                aggregate.filter_json,
                aggregate.metric_name,
                aggregate.metric_version,
            )
            values, _, source_episode_ids = self._compute(spec)
            current = _input_fingerprint(
                self.policy.version,
                spec,
                values,
                aggregate.statistic,
                source_episode_ids=source_episode_ids,
            )
            result.append(
                AggregateRecord(
                    id=aggregate.id,
                    container_type=aggregate.container_type,
                    container_id=aggregate.container_id,
                    measurement_target_type=aggregate.measurement_target_type,
                    filter_json=aggregate.filter_json,
                    metric_name=aggregate.metric_name,
                    metric_version=aggregate.metric_version,
                    statistic=aggregate.statistic,
                    aggregate_policy_version=aggregate.aggregate_policy_version,
                    value_real=aggregate.value_real,
                    source_measurement_count=aggregate.source_measurement_count,
                    sample_count=aggregate.sample_count,
                    work_count=aggregate.work_count,
                    skipped_target_count=aggregate.skipped_target_count,
                    filter_state_fingerprint=aggregate.filter_state_fingerprint,
                    input_fingerprint=aggregate.input_fingerprint,
                    warning_json=aggregate.warning_json,
                    created_at=aggregate.created_at,
                    stale=(
                        aggregate.aggregate_policy_version != self.policy.version
                        or aggregate.input_fingerprint != current
                    ),
                )
            )
        return tuple(result)

    def _compute(
        self, spec: AggregateSpec
    ) -> tuple[tuple[_Target, ...], tuple[str, ...], tuple[int, ...]]:
        self._current_runs.clear()
        definition = METRIC_DEFINITIONS.get(spec.metric_name)
        if definition is None or definition.version != spec.metric_version:
            raise ValidationError("METRIC_NOT_FOUND")
        filter_value = _parse_filter(spec.filter_json, spec.measurement_target_type)
        episode_ids = self._episode_ids(spec.container_type, spec.container_id)
        targets: list[_Target] = []
        warnings: list[str] = []
        for episode_id in episode_ids:
            document_row = self._connection.execute(
                "SELECT re.reference_work_id, sd.id, sd.current_text_revision_id, "
                "sd.current_structure_revision_id "
                "FROM style_reference_episodes re "
                "LEFT JOIN style_documents sd ON sd.reference_episode_id = re.id "
                "WHERE re.id = ?",
                (episode_id,),
            ).fetchone()
            if document_row is None or document_row[1] is None:
                warnings.append(f"SOURCE_DOCUMENT_UNAVAILABLE:{episode_id}")
                if spec.measurement_target_type == "document":
                    targets.append(
                        _Target(
                            ("episode", episode_id),
                            None,
                            None,
                            0,
                            int(document_row[0]) if document_row else 0,
                            "match",
                            (),
                        )
                    )
                continue
            work_id = int(document_row[0])
            document_id = int(document_row[1])
            text_revision_id = document_row[2]
            structure_id = document_row[3]
            if spec.measurement_target_type == "document":
                measurement = self._current_measurement(
                    document_id, text_revision_id, structure_id, spec
                )
                targets.append(
                    _Target(
                        ("episode", episode_id, "document", document_id),
                        measurement[0] if measurement else None,
                        measurement[1] if measurement else None,
                        measurement[2] if measurement else 0,
                        work_id,
                        "match",
                        (),
                    )
                )
                continue
            if (
                structure_id is None
                or text_revision_id is None
                or not self._structure_belongs(
                    document_id, int(structure_id), int(text_revision_id)
                )
            ):
                warnings.append(f"SOURCE_DOCUMENT_UNAVAILABLE:{episode_id}")
                continue
            scenes = self._connection.execute(
                "SELECT id FROM style_scenes WHERE structure_revision_id = ? "
                "ORDER BY order_index, id",
                (structure_id,),
            ).fetchall()
            semantic_run = self._current_run(
                document_id,
                int(text_revision_id),
                int(structure_id),
                "scene-semantic-classifier",
            )
            for (scene_id_raw,) in scenes:
                scene_id = int(scene_id_raw)
                filter_result, state, unavailable = self._scene_filter(
                    scene_id, semantic_run, filter_value
                )
                warnings.extend(unavailable)
                measurement = None
                if filter_result == "match":
                    measurement = self._current_measurement(
                        document_id, text_revision_id, structure_id, spec, scene_id
                    )
                targets.append(
                    _Target(
                        ("episode", episode_id, "scene", scene_id),
                        measurement[0] if measurement else None,
                        measurement[1] if measurement else None,
                        measurement[2] if measurement else 0,
                        work_id,
                        filter_result,
                        state,
                    )
                )
        return tuple(targets), tuple(sorted(set(warnings))), episode_ids

    def _episode_ids(
        self, container_type: ContainerType, container_id: int
    ) -> tuple[int, ...]:
        if container_type == "corpus":
            return self.corpora.list_effective_episode_ids(container_id)
        row = self._connection.execute(
            "SELECT id FROM style_reference_works WHERE id = ?", (container_id,)
        ).fetchone()
        if row is None:
            raise ValidationError("REFERENCE_WORK_NOT_FOUND")
        rows = self._connection.execute(
            "SELECT id FROM style_reference_episodes WHERE reference_work_id = ? "
            "ORDER BY order_index, id",
            (container_id,),
        ).fetchall()
        return tuple(int(item[0]) for item in rows)

    def _current_measurement(
        self,
        document_id: int,
        text_revision_id: object,
        structure_id: object,
        spec: AggregateSpec,
        scene_id: int | None = None,
    ) -> tuple[int, float, int] | None:
        if text_revision_id is None or structure_id is None:
            return None
        run = self._current_run(
            document_id,
            int(cast(int, text_revision_id)),
            int(cast(int, structure_id)),
            "style-metrics-basic"
            if METRIC_DEFINITIONS[spec.metric_name].group == "basic"
            else "style-metrics-semantic",
        )
        if run is None:
            return None
        target_type = "scene" if scene_id is not None else "document"
        target_id = scene_id if scene_id is not None else document_id
        row = self._connection.execute(
            "SELECT id, CASE WHEN value_int IS NULL THEN value_real "
            "ELSE value_int END, "
            "sample_count FROM style_measurements WHERE analysis_run_id = ? "
            "AND structure_revision_id = ? AND target_type = ? AND target_id = ? "
            "AND metric_name = ? AND metric_version = ?",
            (
                run.id,
                int(cast(int, structure_id)),
                target_type,
                target_id,
                spec.metric_name,
                spec.metric_version,
            ),
        ).fetchone()
        if row is None:
            return None
        return int(row[0]), float(row[1]), int(row[2])

    def _current_run(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        analyzer_id: str,
    ) -> Any | None:
        return self._current_runs.resolve(
            document_id, text_revision_id, structure_id, analyzer_id
        )

    def _structure_belongs(
        self, document_id: int, structure_id: int, text_id: int
    ) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM style_structure_revisions sr "
            "JOIN style_text_revisions tr ON tr.id = sr.text_revision_id "
            "WHERE sr.id = ? AND tr.document_id = ? AND sr.text_revision_id = ?",
            (structure_id, document_id, text_id),
        ).fetchone()
        return row is not None

    def _scene_filter(
        self,
        scene_id: int,
        semantic_run: Any | None,
        filter_value: dict[str, list[str]],
    ) -> tuple[str, tuple[dict[str, JsonValue], ...], tuple[str, ...]]:
        if not filter_value:
            return "match", (), ()
        annotations: dict[str, tuple[object, object]] = {}
        if semantic_run is not None:
            rows = self._connection.execute(
                "SELECT annotation_type, value_json, confidence FROM style_annotations "
                "WHERE analysis_run_id = ? AND subject_type = 'scene' "
                "AND subject_id = ?",
                (semantic_run.id, scene_id),
            ).fetchall()
            annotations = {str(row[0]): (row[1], row[2]) for row in rows}
        state: list[dict[str, JsonValue]] = []
        unavailable: list[str] = []
        for axis, expected in sorted(filter_value.items()):
            annotation = annotations.get(f"scene.{axis}")
            values, source = _effective_axis_values(axis, annotation)
            state.append(
                {
                    "scene_id": scene_id,
                    "axis": axis,
                    "source": source,
                    "effective_value": cast(JsonValue, values)
                    if values is not None
                    else None,
                }
            )
            if values is None:
                unavailable.append(f"SCENE_SELECTOR_UNAVAILABLE:{axis}")
                return "unknown", tuple(state), tuple(unavailable)
            if not set(values).intersection(expected):
                return "non-match", tuple(state), ()
        return "match", tuple(state), tuple(unavailable)
