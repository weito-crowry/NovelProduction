from __future__ import annotations

import sqlite3

from novel_core.errors import ValidationError
from novel_core.style_analysis.structure_models import StructureRevisionRecord
from novel_core.style_analysis.text_service import StyleTextService

_STRUCTURE_REVISION_COLUMNS = (
    "sr.id, sr.text_revision_id, sr.revision_no, sr.segmenter_id, "
    "sr.segmenter_version, sr.source_kind, sr.parent_structure_revision_id, "
    "sr.fingerprint, sr.created_at"
)


class StyleStructureService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._text_service = StyleTextService(connection)

    def get_structure_revision(
        self, document_id: int, revision_id: int
    ) -> StructureRevisionRecord:
        row = self._connection.execute(
            f"SELECT {_STRUCTURE_REVISION_COLUMNS} "
            "FROM style_structure_revisions AS sr "
            "JOIN style_text_revisions AS tr ON tr.id = sr.text_revision_id "
            "WHERE tr.document_id = ? AND sr.id = ?",
            (document_id, revision_id),
        ).fetchone()
        if row is None:
            raise ValidationError("STRUCTURE_REVISION_DOCUMENT_MISMATCH")
        return StructureRevisionRecord(*row)

    def set_current_structure(self, document_id: int, revision_id: int) -> None:
        document = self._text_service.get_document(document_id)
        if document is None:
            raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
        structure = self.get_structure_revision(document_id, revision_id)
        if (
            document.current_text_revision_id is None
            or structure.text_revision_id != document.current_text_revision_id
        ):
            raise ValidationError("CURRENT_STRUCTURE_TEXT_MISMATCH")
        if document.current_structure_revision_id == revision_id:
            return

        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                "UPDATE style_documents SET current_structure_revision_id = ? "
                "WHERE id = ?",
                (revision_id, document_id),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
