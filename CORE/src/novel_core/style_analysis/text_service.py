from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.fingerprints import (
    JsonObject,
    JsonValue,
    fingerprint_json,
)
from novel_core.style_analysis.normalization import (
    NORMALIZER_ID,
    NORMALIZER_VERSION,
    normalize_text,
)
from novel_core.style_analysis.text_models import (
    StyleDocumentRecord,
    TextRevisionRecord,
)

_DOCUMENT_COLUMNS = (
    "id, kind, reference_episode_id, project_work_id, project_episode_id, "
    "current_text_revision_id, current_structure_revision_id, created_at"
)
_TEXT_REVISION_COLUMNS = (
    "id, document_id, revision_no, source_snapshot_id, project_draft_id, "
    "raw_text, canonical_text, raw_sha256, canonical_sha256, "
    "normalization_input_fingerprint, normalizer_id, normalizer_version, "
    "metadata_json, created_at"
)
_PROVISIONAL_NORMALIZER_ID = "sa-b-provisional-raw-bridge"
_PROVISIONAL_NORMALIZER_VERSION = 1


class StyleTextService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_document(self, document_id: int) -> StyleDocumentRecord | None:
        row = self._connection.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        return None if row is None else StyleDocumentRecord(*row)

    def get_text_revision(
        self, document_id: int, revision_id: int
    ) -> TextRevisionRecord:
        row = self._connection.execute(
            f"SELECT {_TEXT_REVISION_COLUMNS} FROM style_text_revisions "
            "WHERE document_id = ? AND id = ?",
            (document_id, revision_id),
        ).fetchone()
        if row is None:
            raise ValidationError("TEXT_REVISION_DOCUMENT_MISMATCH")
        return TextRevisionRecord(*row)

    def insert_reference_revision(
        self,
        *,
        document_id: int,
        source_snapshot_id: int,
        raw_text: str,
        structure_hints_raw: object,
    ) -> TextRevisionRecord:
        """Insert or reuse the initial reference text revision.

        The caller owns the transaction. SA-B stores the adapter serialization as
        the canonical text bridge; the full canonical normalizer is SA-C scope.
        """
        document = self.get_document(document_id)
        if document is None:
            raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
        if (
            document.kind != "reference_episode"
            or document.reference_episode_id is None
        ):
            raise ValidationError("REFERENCE_DOCUMENT_REQUIRED")

        snapshot_row = self._connection.execute(
            "SELECT source_id FROM style_source_snapshots WHERE id = ?",
            (source_snapshot_id,),
        ).fetchone()
        if snapshot_row is None:
            raise ValidationError("SOURCE_SNAPSHOT_NOT_FOUND")
        document_source_row = self._connection.execute(
            "SELECT rw.source_id FROM style_reference_episodes AS re "
            "JOIN style_reference_works AS rw ON rw.id = re.reference_work_id "
            "WHERE re.id = ?",
            (document.reference_episode_id,),
        ).fetchone()
        if document_source_row is None:
            raise ValidationError("REFERENCE_EPISODE_NOT_FOUND")
        if document_source_row[0] != snapshot_row[0]:
            raise ValidationError("SOURCE_SNAPSHOT_DOCUMENT_MISMATCH")

        offsets = _normalize_scene_break_offsets(structure_hints_raw, len(raw_text))
        raw_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        structure_hints: JsonObject = {
            "scene_break_offsets_raw": cast(JsonValue, offsets)
        }
        fingerprint_input: JsonObject = {
            "raw_sha256": raw_sha256,
            "normalizer_id": _PROVISIONAL_NORMALIZER_ID,
            "normalizer_version": _PROVISIONAL_NORMALIZER_VERSION,
            "structure_hints_raw": structure_hints,
        }
        normalization_input_fingerprint = fingerprint_json(fingerprint_input)
        existing_row = self._connection.execute(
            "SELECT id FROM style_text_revisions "
            "WHERE document_id = ? AND normalization_input_fingerprint = ?",
            (document_id, normalization_input_fingerprint),
        ).fetchone()
        if existing_row is not None:
            revision_id = cast(int, existing_row[0])
            if document.current_text_revision_id != revision_id:
                self._connection.execute(
                    "UPDATE style_documents SET current_text_revision_id = ?, "
                    "current_structure_revision_id = NULL WHERE id = ?",
                    (revision_id, document_id),
                )
            return self.get_text_revision(document_id, revision_id)

        revision_no = self._connection.execute(
            "SELECT COALESCE(MAX(revision_no), 0) + 1 "
            "FROM style_text_revisions WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]
        metadata: JsonObject = {
            "normalization_input": fingerprint_input,
            "structure_hints_raw": structure_hints,
        }
        cursor = self._connection.execute(
            "INSERT INTO style_text_revisions "
            "(document_id, revision_no, source_snapshot_id, raw_text, "
            "canonical_text, raw_sha256, canonical_sha256, "
            "normalization_input_fingerprint, normalizer_id, "
            "normalizer_version, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id,
                revision_no,
                source_snapshot_id,
                raw_text,
                raw_text,
                raw_sha256,
                raw_sha256,
                normalization_input_fingerprint,
                _PROVISIONAL_NORMALIZER_ID,
                _PROVISIONAL_NORMALIZER_VERSION,
                _json(metadata),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("reference text revision insert did not return an id")
        revision_id = cursor.lastrowid
        self._connection.execute(
            "UPDATE style_documents SET current_text_revision_id = ?, "
            "current_structure_revision_id = NULL WHERE id = ?",
            (revision_id, document_id),
        )
        return self.get_text_revision(document_id, revision_id)

    def insert_normalized_reference_revision(
        self,
        *,
        document_id: int,
        source_snapshot_id: int,
        raw_text: str,
        structure_hints_raw: object,
    ) -> TextRevisionRecord:
        """Insert or reuse an SA-C formal normalized reference revision.

        The SA-B ``insert_reference_revision`` method intentionally remains a
        provisional compatibility seam. Existing provisional rows are never
        rewritten; this method creates the formal revision for new/reprocessed
        input and persists its raw-to-canonical mapping.
        """
        document = self._validate_reference_revision_input(
            document_id=document_id,
            source_snapshot_id=source_snapshot_id,
        )
        normalized = normalize_text(raw_text, structure_hints_raw)
        raw_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        canonical_sha256 = hashlib.sha256(
            normalized.canonical_text.encode("utf-8")
        ).hexdigest()
        structure_hints_raw_value = _normalize_scene_break_offsets(
            structure_hints_raw, len(raw_text)
        )
        fingerprint_input: JsonObject = {
            "raw_sha256": raw_sha256,
            "normalizer_id": NORMALIZER_ID,
            "normalizer_version": NORMALIZER_VERSION,
            "structure_hints_raw": {
                "scene_break_offsets_raw": cast(JsonValue, structure_hints_raw_value)
            },
        }
        normalization_input_fingerprint = fingerprint_json(fingerprint_input)
        existing_row = self._connection.execute(
            "SELECT id FROM style_text_revisions "
            "WHERE document_id = ? AND normalization_input_fingerprint = ?",
            (document_id, normalization_input_fingerprint),
        ).fetchone()
        if existing_row is not None:
            revision_id = cast(int, existing_row[0])
            if document.current_text_revision_id != revision_id:
                self._connection.execute(
                    "UPDATE style_documents SET current_text_revision_id = ?, "
                    "current_structure_revision_id = NULL WHERE id = ?",
                    (revision_id, document_id),
                )
            return self.get_text_revision(document_id, revision_id)

        revision_no = self._connection.execute(
            "SELECT COALESCE(MAX(revision_no), 0) + 1 "
            "FROM style_text_revisions WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]
        metadata: JsonObject = {
            "normalization_input": fingerprint_input,
            "structure_hints_raw": {
                "scene_break_offsets_raw": cast(JsonValue, structure_hints_raw_value)
            },
            "structure_hints": {
                "scene_break_offsets_cp": cast(
                    JsonValue, list(normalized.scene_break_offsets_cp)
                )
            },
            "normalization_warnings": cast(JsonValue, list(normalized.warnings)),
        }
        cursor = self._connection.execute(
            "INSERT INTO style_text_revisions "
            "(document_id, revision_no, source_snapshot_id, raw_text, "
            "canonical_text, raw_sha256, canonical_sha256, "
            "normalization_input_fingerprint, normalizer_id, "
            "normalizer_version, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id,
                revision_no,
                source_snapshot_id,
                raw_text,
                normalized.canonical_text,
                raw_sha256,
                canonical_sha256,
                normalization_input_fingerprint,
                NORMALIZER_ID,
                NORMALIZER_VERSION,
                _json(metadata),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("normalized text revision insert did not return an id")
        revision_id = cursor.lastrowid
        self._connection.executemany(
            "INSERT INTO style_text_mappings "
            "(text_revision_id, segment_order, raw_start, raw_end, "
            "canonical_start, canonical_end, operation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    revision_id,
                    order_index,
                    segment.raw_start,
                    segment.raw_end,
                    segment.canonical_start,
                    segment.canonical_end,
                    segment.operation,
                )
                for order_index, segment in enumerate(normalized.segments, start=1)
            ),
        )
        self._connection.execute(
            "UPDATE style_documents SET current_text_revision_id = ?, "
            "current_structure_revision_id = NULL WHERE id = ?",
            (revision_id, document_id),
        )
        return self.get_text_revision(document_id, revision_id)

    def _validate_reference_revision_input(
        self, *, document_id: int, source_snapshot_id: int
    ) -> StyleDocumentRecord:
        document = self.get_document(document_id)
        if document is None:
            raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
        if (
            document.kind != "reference_episode"
            or document.reference_episode_id is None
        ):
            raise ValidationError("REFERENCE_DOCUMENT_REQUIRED")
        snapshot_row = self._connection.execute(
            "SELECT source_id FROM style_source_snapshots WHERE id = ?",
            (source_snapshot_id,),
        ).fetchone()
        if snapshot_row is None:
            raise ValidationError("SOURCE_SNAPSHOT_NOT_FOUND")
        document_source_row = self._connection.execute(
            "SELECT rw.source_id FROM style_reference_episodes AS re "
            "JOIN style_reference_works AS rw ON rw.id = re.reference_work_id "
            "WHERE re.id = ?",
            (document.reference_episode_id,),
        ).fetchone()
        if document_source_row is None:
            raise ValidationError("REFERENCE_EPISODE_NOT_FOUND")
        if document_source_row[0] != snapshot_row[0]:
            raise ValidationError("SOURCE_SNAPSHOT_DOCUMENT_MISMATCH")
        return document

    def set_current_text(self, document_id: int, revision_id: int) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            document = self.get_document(document_id)
            if document is None:
                raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
            self.get_text_revision(document_id, revision_id)
            if document.current_text_revision_id == revision_id:
                self._connection.commit()
                return
            self._connection.execute(
                "UPDATE style_documents "
                "SET current_text_revision_id = ?, "
                "current_structure_revision_id = NULL WHERE id = ?",
                (revision_id, document_id),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise


def _normalize_scene_break_offsets(value: object, text_length: int) -> list[int]:
    if not isinstance(value, list) or any(
        not isinstance(offset, int) or isinstance(offset, bool) for offset in value
    ):
        raise ValidationError("STRUCTURE_HINTS_INVALID")
    offsets = sorted(set(cast(list[int], value)))
    if any(offset < 0 or offset > text_length for offset in offsets):
        raise ValidationError("STRUCTURE_HINTS_INVALID")
    return offsets


def _json(value: JsonObject) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
