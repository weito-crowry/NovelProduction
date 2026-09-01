from __future__ import annotations

import json
import sqlite3

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
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

    def list_analysis_runs(self, document_id: int) -> tuple[object, ...]:
        rows = self._connection.execute(
            "SELECT id FROM style_analysis_runs WHERE document_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (document_id,),
        ).fetchall()
        return tuple(
            run for row in rows if (run := self._runs.get_run(int(row[0]))) is not None
        )

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
        self, document_id: int, *, min_confidence: float = 0.60
    ) -> tuple[dict[str, object], ...]:
        rows = self._connection.execute(
            "SELECT a.id, a.subject_id, a.value_json, a.confidence, "
            "a.analysis_run_id "
            "FROM style_annotations a "
            "JOIN style_analysis_runs r ON r.id = a.analysis_run_id "
            "WHERE r.document_id = ? "
            "AND a.annotation_type = 'scene_boundary_candidate' "
            "AND a.confidence >= ? ORDER BY a.id",
            (document_id, min_confidence),
        ).fetchall()
        return tuple(
            {
                "id": row[0],
                "scene_id": row[1],
                "value": json.loads(row[2]),
                "confidence": row[3],
                "analysis_run_id": row[4],
            }
            for row in rows
        )
