from __future__ import annotations

import json
import sqlite3

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.runtime_models import AnalysisRunRecord
from novel_core.style_analysis.semantic_models import AnnotationRecord
from novel_core.style_analysis.semantic_repository import SemanticRepository
from novel_core.style_analysis.source_models import (
    ReferenceEpisodeRecord,
    ReferenceWorkRecord,
)
from novel_core.style_analysis.source_repository import StyleSourceRepository


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
        runs = self.list_analysis_runs(document_id)
        selected = tuple(
            run for run in runs if run.structure_revision_id == structure_revision_id
        )
        run_ids = [run.id for run in selected]
        outputs = [
            output for run_id in run_ids for output in self.list_run_outputs(run_id)
        ]
        return {
            "structure_revision_id": structure_revision_id,
            "analysis_run_ids": run_ids,
            "outputs": outputs,
        }

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
        basic_current = any(
            run.status == "succeeded"
            and run.text_revision_id == text_revision_id
            and run.structure_revision_id == structure_revision_id
            for run in basic_history
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
        current_semantic = tuple(
            run
            for run in semantic_history
            if run.text_revision_id == text_revision_id
            and run.structure_revision_id == structure_revision_id
        )
        current_by_analyzer: dict[str, AnalysisRunRecord] = {}
        for run in current_semantic:
            current_by_analyzer.setdefault(run.analyzer_id, run)
        if semantic_ids.issubset(current_by_analyzer) and all(
            run.status == "succeeded" for run in current_by_analyzer.values()
        ):
            semantic = {"state": "current", "reasons": []}
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
