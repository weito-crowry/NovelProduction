from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from novel_core.style_analysis.aggregate_repository import MeasurementRepository
from novel_core.style_analysis.aggregate_service import AggregateService
from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.metrics import BASIC_METRIC_DEFINITIONS
from novel_core.style_analysis.profile_service import ProfileService
from novel_core.style_analysis.review_service import ReviewService
from novel_core.style_analysis.runtime_models import AnalysisRunRecord
from novel_core.style_analysis.semantic_repository import SemanticRepository
from novel_core.style_analysis.source_models import (
    ReferenceEpisodeRecord,
    ReferenceWorkRecord,
)
from novel_core.style_analysis.source_repository import StyleSourceRepository
from novel_core.style_analysis.structure_service import StyleStructureService
from novel_core.style_analysis.term_service import TermService
from novel_core.style_analysis.text_service import StyleTextService

from novel_api.style_analysis.catalog_corpus_profile import (
    StyleAnalysisCorpusProfileMixin,
)
from novel_api.style_analysis.catalog_current import (
    resolution_state_changed,
    select_current_runs,
)
from novel_api.style_analysis.catalog_documents import StyleAnalysisDocumentsMixin
from novel_api.style_analysis.catalog_effective import effective_outputs
from novel_api.style_analysis.catalog_lint import StyleAnalysisLintMixin
from novel_api.style_analysis.catalog_outputs import StyleAnalysisOutputsMixin
from novel_api.style_analysis.catalog_review import StyleAnalysisReviewMixin
from novel_api.style_analysis.job_service import DatabaseConnection

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


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class StyleAnalysisCatalogService(
    StyleAnalysisDocumentsMixin,
    StyleAnalysisCorpusProfileMixin,
    StyleAnalysisOutputsMixin,
    StyleAnalysisReviewMixin,
    StyleAnalysisLintMixin,
):
    def __init__(self, connection: DatabaseConnection) -> None:
        self._repository = StyleSourceRepository(cast(Any, connection))
        self._connection = connection
        self._runs = AnalysisRunRepository(cast(Any, connection))
        self._annotations = SemanticRepository(cast(Any, connection))
        self._measurements = MeasurementRepository(cast(Any, connection))
        self._aggregate_service = AggregateService(cast(Any, connection))
        self._profile_service = ProfileService(cast(Any, connection))
        self._entities = EntityService(cast(Any, connection))
        self._terms = TermService(cast(Any, connection))
        self._reviews = ReviewService(cast(Any, connection))
        self._text = StyleTextService(cast(Any, connection))
        self._structure = StyleStructureService(cast(Any, connection))
        from novel_core.style_analysis.lint_service import StyleLintService

        self._lint = StyleLintService(cast(Any, connection))

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
        return tuple(
            {
                "id": measurement.id,
                "analysis_run_id": measurement.analysis_run_id,
                "structure_revision_id": measurement.structure_revision_id,
                "target_type": measurement.target_type,
                "target_id": measurement.target_id,
                "metric_name": measurement.metric_name,
                "metric_version": measurement.metric_version,
                "value": measurement.value,
                "sample_count": measurement.sample_count,
                "created_at": measurement.created_at,
            }
            for measurement in self._measurements.list_for_run(run_id)
        )

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
        inference_targets = self.inference_targets_for_runs(tuple(run_ids))
        entities = self._entities_for_document(document_id)
        terms = self._terms_for_document(document_id)
        mentions = self._mentions_for_runs(
            tuple(
                run.id
                for run in selected
                if run.analyzer_id == "entity-mention-extractor"
            )
        )
        term_resolver_run_ids = tuple(
            run.id for run in selected if run.analyzer_id == "term-resolver"
        )
        term_mentions = self._term_mentions_for_runs(term_resolver_run_ids)
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
            terms=terms,
            structure_revision_id=structure_revision_id,
            term_resolver_run_ids=term_resolver_run_ids,
        )
        return {
            "structure_revision_id": structure_revision_id,
            "analysis_run_ids": run_ids,
            "outputs": outputs,
            **by_type,
            "raw": raw,
            "inference_targets": inference_targets,
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
        return select_current_runs(
            self,
            document_id,
            text_revision_id,
            structure_revision_id,
            analyzer_ids,
        )

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
        terms: Sequence[dict[str, object]] = (),
        structure_revision_id: int | None = None,
        term_resolver_run_ids: Sequence[int] = (),
    ) -> dict[str, list[dict[str, object]]]:
        return effective_outputs(
            self,
            outputs,
            mentions=mentions,
            terms=terms,
            structure_revision_id=structure_revision_id,
            term_resolver_run_ids=term_resolver_run_ids,
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
        lineage_changed = resolution_state_changed(
            self,
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
        elif current_by_analyzer and (not state_current or lineage_changed):
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
        return resolution_state_changed(
            self,
            document_id,
            text_revision_id,
            structure_revision_id,
            tuple(history),
            current,
        )

    def _semantic_runs_have_current_inputs(
        self,
        document_id: int,
        structure_revision_id: int | None,
        runs: dict[str, AnalysisRunRecord],
    ) -> bool:
        if structure_revision_id is None:
            return False
        orchestrator = DocumentAnalysisOrchestrator(
            cast(Any, self._connection),
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
