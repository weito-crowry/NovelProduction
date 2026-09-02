from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from novel_core.style_analysis.semantic_models import AnnotationRecord


class StyleAnalysisOutputsMixin:
    _annotations: Any
    _connection: Any

    def inference_targets_for_runs(
        self, run_ids: Sequence[int]
    ) -> list[dict[str, object]]:
        if not run_ids:
            return []
        placeholders = ",".join("?" for _ in run_ids)
        targets: list[dict[str, object]] = []
        entity_rows = self._connection.execute(
            "SELECT id, alias, analysis_run_id, created_at "
            "FROM style_entity_aliases "
            "WHERE origin = 'inferred' AND analysis_run_id IN ("
            f"{placeholders}) ORDER BY id",
            tuple(run_ids),
        ).fetchall()
        for alias_id, alias, analysis_run_id, created_at in entity_rows:
            targets.append(
                {
                    "id": alias_id,
                    "annotation_type": "entity_alias",
                    "subject_type": "entity_alias",
                    "subject_id": alias_id,
                    "field_path": "entity_alias.acceptance",
                    "value": {"alias": alias},
                    "confidence": None,
                    "analysis_run_id": analysis_run_id,
                    "start_cp": None,
                    "end_cp": None,
                    "created_at": created_at,
                }
            )
        term_rows = self._connection.execute(
            "SELECT id, alias, analysis_run_id, created_at "
            "FROM style_term_aliases "
            "WHERE origin = 'inferred' AND analysis_run_id IN ("
            f"{placeholders}) ORDER BY id",
            tuple(run_ids),
        ).fetchall()
        for alias_id, alias, analysis_run_id, created_at in term_rows:
            targets.append(
                {
                    "id": alias_id,
                    "annotation_type": "term_alias",
                    "subject_type": "term_alias",
                    "subject_id": alias_id,
                    "field_path": "term_alias.acceptance",
                    "value": {"alias": alias},
                    "confidence": None,
                    "analysis_run_id": analysis_run_id,
                    "start_cp": None,
                    "end_cp": None,
                    "created_at": created_at,
                }
            )
        return targets

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
