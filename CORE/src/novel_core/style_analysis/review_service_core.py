from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.review_models import (
    InferenceReviewRecord,
    ManualOverrideRecord,
    ReviewItemRecord,
)
from novel_core.style_analysis.review_support import (
    CLEARABLE_FIELDS,
    INFERENCE_ANALYZERS,
    INFERENCE_REVIEW_FIELDS,
    OVERRIDE_FIELDS,
    REVIEW_ITEM_SUBJECT_TYPES,
)
from novel_core.style_analysis.review_validation import ReviewValidationMixin


class ReviewService(ReviewValidationMixin):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_manual_review_item(
        self,
        *,
        subject_type: str,
        subject_id: int,
        analysis_run_id: int | None = None,
        priority: str = "normal",
    ) -> ReviewItemRecord:
        if subject_type not in REVIEW_ITEM_SUBJECT_TYPES:
            raise ValueError("REVIEW_SUBJECT_TYPE_INVALID")
        if priority not in {"normal", "high"}:
            raise ValueError("REVIEW_PRIORITY_INVALID")
        info = self._subject_info(subject_type, subject_id)
        if analysis_run_id is not None:
            self._validate_run_scope(analysis_run_id, info)
        evidence = self._evidence(subject_type, subject_id, info)
        with self._write_transaction():
            cursor = self._connection.execute(
                "INSERT INTO style_review_items "
                "(document_id, reference_work_id, item_type, subject_type, subject_id, "
                "analysis_run_id, priority, status, reason_code, evidence_json) "
                "VALUES (?, ?, 'manual_review', ?, ?, ?, ?, 'open', 'user_marked', ?)",
                (
                    info.document_id,
                    info.reference_work_id,
                    subject_type,
                    subject_id,
                    analysis_run_id,
                    priority,
                    _json(evidence),
                ),
            )
            assert cursor.lastrowid is not None
            return self.get_review_item(cursor.lastrowid) or _missing()

    def get_review_item(self, review_item_id: int) -> ReviewItemRecord | None:
        row = self._connection.execute(
            "SELECT id, document_id, reference_work_id, item_type, subject_type, "
            "subject_id, analysis_run_id, priority, status, reason_code, "
            "evidence_json, resolution_note, version, created_at, resolved_at "
            "FROM style_review_items WHERE id = ?",
            (review_item_id,),
        ).fetchone()
        return None if row is None else ReviewItemRecord(*row)

    def list_review_items(
        self, *, status: str | None = None
    ) -> tuple[ReviewItemRecord, ...]:
        if status is not None and status not in {
            "open",
            "resolved",
            "ignored",
            "superseded",
        }:
            raise ValueError("REVIEW_STATUS_INVALID")
        query = (
            "SELECT id, document_id, reference_work_id, item_type, subject_type, "
            "subject_id, analysis_run_id, priority, status, reason_code, "
            "evidence_json, resolution_note, version, created_at, resolved_at "
            "FROM style_review_items"
        )
        parameters: tuple[object, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY created_at DESC, id DESC"
        return tuple(
            ReviewItemRecord(*row)
            for row in self._connection.execute(query, parameters)
        )

    def resolve_review_item(
        self, review_item_id: int, *, expected_version: int, note: str | None
    ) -> ReviewItemRecord:
        return self._close_review_item(
            review_item_id, expected_version, note, "resolved"
        )

    def ignore_review_item(
        self, review_item_id: int, *, expected_version: int, note: str | None
    ) -> ReviewItemRecord:
        return self._close_review_item(
            review_item_id, expected_version, note, "ignored"
        )

    def supersede_review_item(self, review_item_id: int) -> ReviewItemRecord:
        with self._write_transaction():
            item = self.get_review_item(review_item_id)
            if item is None:
                raise ValueError("REVIEW_ITEM_NOT_FOUND")
            if item.status != "open":
                raise ValueError("REVIEW_ITEM_CLOSED")
            self._connection.execute(
                "UPDATE style_review_items SET status='superseded', version=version+1, "
                "resolved_at=CURRENT_TIMESTAMP WHERE id = ? AND status='open'",
                (review_item_id,),
            )
            return self.get_review_item(review_item_id) or _missing()

    def create_override(
        self,
        *,
        subject_type: str,
        subject_id: int,
        field_path: str,
        operation: str,
        value: object = None,
        document_id: int | None = None,
        reference_work_id: int | None = None,
        base_analysis_run_id: int | None = None,
        structure_revision_id: int | None = None,
        note: str | None = None,
    ) -> ManualOverrideRecord:
        if (
            subject_type not in OVERRIDE_FIELDS
            or field_path not in OVERRIDE_FIELDS[subject_type]
        ):
            raise ValueError("OVERRIDE_TARGET_INVALID")
        if operation not in {"set", "clear", "revert"}:
            raise ValueError("OVERRIDE_OPERATION_INVALID")
        if operation != "set" and value is not None:
            raise ValueError("OVERRIDE_VALUE_INVALID")
        info = self._subject_info(subject_type, subject_id)
        self._validate_requested_scope(info, document_id, reference_work_id)
        self._validate_override_lineage(subject_type, info, structure_revision_id)
        if base_analysis_run_id is not None:
            self._validate_run_scope(base_analysis_run_id, info)
        if operation == "clear" and field_path not in CLEARABLE_FIELDS:
            raise ValueError("OVERRIDE_CLEAR_INVALID")
        if operation == "set":
            self._validate_value(subject_type, field_path, value, info, subject_id)
            value_json = _json(value)
        else:
            value_json = None
        with self._write_transaction():
            if operation == "revert" and not self._has_active_override(
                subject_type, subject_id, field_path
            ):
                raise ValueError("OVERRIDE_NOT_FOUND")
            cursor = self._connection.execute(
                "INSERT INTO style_manual_overrides "
                "(document_id, reference_work_id, subject_type, subject_id, "
                "field_path, operation, value_json, base_analysis_run_id, "
                "structure_revision_id, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    info.document_id,
                    info.reference_work_id,
                    subject_type,
                    subject_id,
                    field_path,
                    operation,
                    value_json,
                    base_analysis_run_id,
                    structure_revision_id,
                    note,
                ),
            )
            assert cursor.lastrowid is not None
            return self.get_override(cursor.lastrowid) or _missing()

    def get_override(self, override_id: int) -> ManualOverrideRecord | None:
        row = self._connection.execute(
            "SELECT id, document_id, reference_work_id, subject_type, subject_id, "
            "field_path, operation, value_json, base_analysis_run_id, "
            "structure_revision_id, note, created_at FROM style_manual_overrides "
            "WHERE id = ?",
            (override_id,),
        ).fetchone()
        return None if row is None else ManualOverrideRecord(*row)

    def list_overrides(
        self, *, subject_type: str | None = None, subject_id: int | None = None
    ) -> tuple[ManualOverrideRecord, ...]:
        query = (
            "SELECT id, document_id, reference_work_id, subject_type, subject_id, "
            "field_path, operation, value_json, base_analysis_run_id, "
            "structure_revision_id, note, created_at FROM style_manual_overrides"
        )
        parameters: list[object] = []
        clauses: list[str] = []
        if subject_type is not None:
            clauses.append("subject_type=?")
            parameters.append(subject_type)
        if subject_id is not None:
            clauses.append("subject_id=?")
            parameters.append(subject_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, id DESC"
        return tuple(
            ManualOverrideRecord(*row)
            for row in self._connection.execute(query, tuple(parameters))
        )

    def create_inference_review(
        self,
        *,
        analysis_run_id: int,
        subject_type: str,
        subject_id: int,
        field_path: str,
        review_status: str,
        note: str | None = None,
    ) -> InferenceReviewRecord:
        if (subject_type, field_path) not in INFERENCE_REVIEW_FIELDS:
            raise ValueError("INFERENCE_REVIEW_TARGET_INVALID")
        if review_status not in {"confirmed", "rejected"}:
            raise ValueError("INFERENCE_REVIEW_STATUS_INVALID")
        if subject_type.endswith("_alias"):
            parent_type = "entity" if subject_type == "entity_alias" else "term"
            parent_column = "entity_id" if parent_type == "entity" else "term_id"
            table = (
                "style_entity_aliases"
                if subject_type == "entity_alias"
                else "style_term_aliases"
            )
            parent = self._connection.execute(
                f"SELECT {parent_column} FROM {table} WHERE id = ?", (subject_id,)
            ).fetchone()
            if parent is None:
                raise ValueError("REVIEW_SUBJECT_NOT_FOUND")
            info = self._subject_info(parent_type, int(parent[0]))
        else:
            info = self._subject_info(subject_type, subject_id)
        self._validate_run_scope(analysis_run_id, info)
        raw_type = INFERENCE_REVIEW_FIELDS[(subject_type, field_path)]
        if subject_type.endswith("_alias"):
            self._validate_alias_review(subject_type, subject_id, analysis_run_id, info)
        else:
            run = self._connection.execute(
                "SELECT document_id, analyzer_id, text_revision_id, "
                "structure_revision_id FROM style_analysis_runs "
                "WHERE id = ?",
                (analysis_run_id,),
            ).fetchone()
            if run is None or run[1] != INFERENCE_ANALYZERS[raw_type]:
                raise ValueError("INFERENCE_REVIEW_SOURCE_NOT_FOUND")
            if (
                info.structure_revision_id is not None
                and int(run[3]) != info.structure_revision_id
            ):
                raise ValueError("INFERENCE_REVIEW_SOURCE_NOT_FOUND")
            current_run = CurrentRunResolver(self._connection).resolve(
                int(run[0]),
                int(run[2]),
                int(run[3]),
                str(run[1]),
            )
            if current_run is None or current_run.id != analysis_run_id:
                raise ValueError("INFERENCE_REVIEW_SOURCE_NOT_FOUND")
            annotation = self._connection.execute(
                "SELECT value_json FROM style_annotations WHERE analysis_run_id = ? "
                "AND subject_type = ? AND subject_id = ? AND annotation_type = ?",
                (analysis_run_id, subject_type, subject_id, raw_type),
            ).fetchone()
            if annotation is None:
                raise ValueError("INFERENCE_REVIEW_SOURCE_NOT_FOUND")
            count = self._connection.execute(
                "SELECT COUNT(*) FROM style_annotations WHERE analysis_run_id = ? "
                "AND subject_type = ? AND subject_id = ? AND annotation_type = ?",
                (analysis_run_id, subject_type, subject_id, raw_type),
            ).fetchone()[0]
            if count != 1:
                raise ValueError("INFERENCE_REVIEW_SOURCE_NOT_FOUND")
            self._validate_annotation_value(
                raw_type, annotation[0], info, subject_type, subject_id
            )
        with self._write_transaction():
            cursor = self._connection.execute(
                "INSERT INTO style_inference_reviews "
                "(document_id, reference_work_id, subject_type, subject_id, "
                "field_path, analysis_run_id, review_status, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    info.document_id,
                    info.reference_work_id,
                    subject_type,
                    subject_id,
                    field_path,
                    analysis_run_id,
                    review_status,
                    note,
                ),
            )
            assert cursor.lastrowid is not None
            return self.get_inference_review(cursor.lastrowid) or _missing()

    def get_inference_review(self, review_id: int) -> InferenceReviewRecord | None:
        row = self._connection.execute(
            "SELECT id, document_id, reference_work_id, subject_type, subject_id, "
            "field_path, analysis_run_id, review_status, note, created_at "
            "FROM style_inference_reviews WHERE id = ?",
            (review_id,),
        ).fetchone()
        return None if row is None else InferenceReviewRecord(*row)

    def list_inference_reviews(
        self, *, analysis_run_id: int | None = None
    ) -> tuple[InferenceReviewRecord, ...]:
        query = (
            "SELECT id, document_id, reference_work_id, subject_type, subject_id, "
            "field_path, analysis_run_id, review_status, note, created_at "
            "FROM style_inference_reviews"
        )
        parameters: tuple[object, ...] = ()
        if analysis_run_id is not None:
            query += " WHERE analysis_run_id=?"
            parameters = (analysis_run_id,)
        query += " ORDER BY created_at DESC, id DESC"
        return tuple(
            InferenceReviewRecord(*row)
            for row in self._connection.execute(query, parameters)
        )

    def _close_review_item(
        self,
        review_item_id: int,
        expected_version: int,
        note: str | None,
        status: str,
    ) -> ReviewItemRecord:
        with self._write_transaction():
            item = self.get_review_item(review_item_id)
            if item is None:
                raise ValueError("REVIEW_ITEM_NOT_FOUND")
            if item.version != expected_version:
                raise ValueError("VERSION_CONFLICT")
            if item.status != "open":
                raise ValueError("REVIEW_ITEM_CLOSED")
            self._connection.execute(
                "UPDATE style_review_items SET status=?, resolution_note=?, "
                "resolved_at=CURRENT_TIMESTAMP, version=version+1 WHERE id=?",
                (status, note, review_item_id),
            )
            return self.get_review_item(review_item_id) or _missing()

    @staticmethod
    def _evidence(
        subject_type: str, subject_id: int, info: object
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "subject_type": subject_type,
            "subject_id": subject_id,
        }
        evidence[f"{subject_type}_id"] = subject_id
        structure_revision_id = getattr(info, "structure_revision_id", None)
        if structure_revision_id is not None:
            evidence["structure_revision_id"] = structure_revision_id
        start_cp = getattr(info, "start_cp", None)
        end_cp = getattr(info, "end_cp", None)
        if start_cp is not None and end_cp is not None:
            evidence["spans"] = [{"start_cp": start_cp, "end_cp": end_cp}]
        block_id = getattr(info, "block_id", None)
        if block_id is not None:
            evidence["block_ids"] = [block_id]
        return evidence

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        savepoint = "style_review_write"
        owns_transaction = not self._connection.in_transaction
        if owns_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        else:
            self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield
            if owns_transaction:
                self._connection.commit()
            else:
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            else:
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("OVERRIDE_VALUE_INVALID") from exc


def _missing() -> Any:
    raise RuntimeError("style review record disappeared")
