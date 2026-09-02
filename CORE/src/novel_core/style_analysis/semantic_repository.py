from __future__ import annotations

import sqlite3

from novel_core.style_analysis.semantic_models import AnnotationRecord


class SemanticRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert_annotation(
        self,
        *,
        annotation_type: str,
        subject_type: str,
        subject_id: int,
        value_json: str,
        confidence: float | None,
        analysis_run_id: int,
        start_cp: int | None = None,
        end_cp: int | None = None,
    ) -> AnnotationRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_annotations "
            "(annotation_type, subject_type, subject_id, value_json, confidence, "
            "analysis_run_id, start_cp, end_cp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                annotation_type,
                subject_type,
                subject_id,
                value_json,
                confidence,
                analysis_run_id,
                start_cp,
                end_cp,
            ),
        )
        assert cursor.lastrowid is not None
        return self.get(cursor.lastrowid)

    def get(self, annotation_id: int) -> AnnotationRecord:
        row = self._connection.execute(
            "SELECT id, annotation_type, subject_type, subject_id, value_json, "
            "confidence, analysis_run_id, start_cp, end_cp, created_at "
            "FROM style_annotations WHERE id = ?",
            (annotation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("ANNOTATION_NOT_FOUND")
        return AnnotationRecord(*row)

    def list_for_run(self, analysis_run_id: int) -> tuple[AnnotationRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, annotation_type, subject_type, subject_id, value_json, "
            "confidence, analysis_run_id, start_cp, end_cp, created_at "
            "FROM style_annotations "
            "WHERE analysis_run_id = ? ORDER BY id",
            (analysis_run_id,),
        ).fetchall()
        return tuple(AnnotationRecord(*row) for row in rows)
