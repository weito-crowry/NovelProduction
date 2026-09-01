from __future__ import annotations

import sqlite3

from novel_core.errors import ValidationError
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
