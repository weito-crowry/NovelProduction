from __future__ import annotations

import json
from typing import Any

from novel_core.style_analysis.semantic_models import AnnotationRecord


class StyleAnalysisOutputsMixin:
    _annotations: Any
    _connection: Any

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
