from __future__ import annotations

import json
import sqlite3
from typing import cast

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.metrics import BASIC_METRIC_DEFINITIONS
from novel_core.style_analysis.runtime_models import AnalysisRunRecord
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
        return tuple(
            self._annotation_response(annotation)
            for annotation in self._annotations.list_for_run(run_id)
        )

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
        term_mentions = self._term_mentions_for_runs(
            tuple(run.id for run in selected if run.analyzer_id == "term-resolver")
        )
        by_type = {
            "entities": entities,
            "mentions": [
                output for output in outputs if output["subject_type"] == "mention"
            ],
            "speakers": [
                output for output in outputs if output["annotation_type"] == "speaker"
            ],
            "terms": terms,
            "term_mentions": term_mentions,
            "explanations": [
                output
                for output in outputs
                if output["annotation_type"] == "term_explanation"
            ],
            "scenes": [
                output for output in outputs if output["subject_type"] == "scene"
            ],
            "blocks": [
                output for output in outputs if output["subject_type"] == "block"
            ],
        }
        by_type["scene_axes"] = by_type["scenes"]
        by_type["pov"] = [
            output for output in outputs if output["annotation_type"] == "scene.pov"
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
        return {
            "structure_revision_id": structure_revision_id,
            "analysis_run_ids": run_ids,
            "outputs": outputs,
            **by_type,
            "raw": outputs,
            "effective": outputs,
            "analysis_status": status,
        }

    def _select_runs(
        self,
        document_id: int,
        text_revision_id: int,
        structure_revision_id: int,
        analyzer_ids: tuple[str, ...],
    ) -> tuple[AnalysisRunRecord, ...]:
        runs = self.list_analysis_runs(document_id)
        selected: list[AnalysisRunRecord] = []
        for analyzer_id in analyzer_ids:
            candidates = [
                run
                for run in runs
                if run.analyzer_id == analyzer_id
                and run.text_revision_id == text_revision_id
                and run.structure_revision_id == structure_revision_id
                and run.status in {"succeeded", "partial"}
            ]
            candidates.sort(
                key=lambda run: (
                    0 if run.status == "succeeded" else 1,
                    -run.id,
                )
            )
            if candidates:
                selected.append(candidates[0])
        return tuple(selected)

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
                tuple(sorted(semantic_ids)),
            )
            if text_revision_id is not None and structure_revision_id is not None
            else ()
        )
        current_by_analyzer = {run.analyzer_id: run for run in current_semantic}
        state_current = self._semantic_runs_have_current_inputs(
            document_id, structure_revision_id, current_by_analyzer
        )
        if (
            semantic_ids.issubset(current_by_analyzer)
            and all(run.status == "succeeded" for run in current_by_analyzer.values())
            and state_current
        ):
            semantic = {"state": "current", "reasons": []}
        elif current_by_analyzer and not state_current:
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
