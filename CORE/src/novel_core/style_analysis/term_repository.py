from __future__ import annotations

import sqlite3

from novel_core.style_analysis.term_models import (
    TermAliasRecord,
    TermMentionRecord,
    TermRecord,
)


class TermRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_inferred(
        self,
        *,
        reference_work_id: int | None,
        document_id: int | None,
        canonical_label: str,
        term_type: str,
        run_id: int,
    ) -> TermRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_terms "
            "(reference_work_id, document_id, canonical_label, term_type, "
            "origin, created_by_run_id) "
            "VALUES (?, ?, ?, ?, 'inferred', ?)",
            (reference_work_id, document_id, canonical_label, term_type, run_id),
        )
        assert cursor.lastrowid is not None
        return self.get(cursor.lastrowid)

    def get(self, term_id: int) -> TermRecord:
        row = self._connection.execute(
            "SELECT id, reference_work_id, document_id, canonical_label, term_type, "
            "origin, created_by_run_id, created_at FROM style_terms WHERE id = ?",
            (term_id,),
        ).fetchone()
        if row is None:
            raise ValueError("TERM_NOT_FOUND")
        return TermRecord(*row)

    def list_for_scope(
        self, *, reference_work_id: int | None = None, document_id: int | None = None
    ) -> tuple[TermRecord, ...]:
        if (reference_work_id is None) == (document_id is None):
            raise ValueError("TERM_SCOPE_INVALID")
        field, value = (
            ("reference_work_id", reference_work_id)
            if reference_work_id is not None
            else ("document_id", document_id)
        )
        rows = self._connection.execute(
            "SELECT id, reference_work_id, document_id, canonical_label, term_type, "
            "origin, created_by_run_id, created_at FROM style_terms "
            f"WHERE {field} = ? ORDER BY id",
            (value,),
        ).fetchall()
        return tuple(TermRecord(*row) for row in rows)

    def insert_alias(
        self, *, term_id: int, alias: str, origin: str, analysis_run_id: int | None
    ) -> TermAliasRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_term_aliases (term_id, alias, origin, analysis_run_id) "
            "VALUES (?, ?, ?, ?)",
            (term_id, alias, origin, analysis_run_id),
        )
        assert cursor.lastrowid is not None
        return self.get_alias(cursor.lastrowid)

    def get_alias(self, alias_id: int) -> TermAliasRecord:
        row = self._connection.execute(
            "SELECT id, term_id, alias, origin, analysis_run_id, created_at "
            "FROM style_term_aliases WHERE id = ?",
            (alias_id,),
        ).fetchone()
        if row is None:
            raise ValueError("TERM_ALIAS_NOT_FOUND")
        return TermAliasRecord(*row)

    def aliases_for(self, term_id: int) -> tuple[TermAliasRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, term_id, alias, origin, analysis_run_id, created_at "
            "FROM style_term_aliases WHERE term_id = ? ORDER BY alias, id",
            (term_id,),
        ).fetchall()
        return tuple(TermAliasRecord(*row) for row in rows)

    def insert_mention(
        self,
        *,
        term_id: int,
        structure_revision_id: int,
        scene_id: int,
        block_id: int,
        start_cp: int,
        end_cp: int,
        surface: str,
        analysis_run_id: int,
    ) -> TermMentionRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_term_mentions "
            "(term_id, structure_revision_id, scene_id, block_id, start_cp, "
            "end_cp, surface, analysis_run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                term_id,
                structure_revision_id,
                scene_id,
                block_id,
                start_cp,
                end_cp,
                surface,
                analysis_run_id,
            ),
        )
        assert cursor.lastrowid is not None
        return self.get_mention(cursor.lastrowid)

    def get_mention(self, mention_id: int) -> TermMentionRecord:
        row = self._connection.execute(
            "SELECT id, term_id, structure_revision_id, scene_id, block_id, start_cp, "
            "end_cp, surface, analysis_run_id FROM style_term_mentions WHERE id = ?",
            (mention_id,),
        ).fetchone()
        if row is None:
            raise ValueError("TERM_MENTION_NOT_FOUND")
        return TermMentionRecord(*row)

    def list_mentions(self, *, analysis_run_id: int) -> tuple[TermMentionRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, term_id, structure_revision_id, scene_id, block_id, start_cp, "
            "end_cp, surface, analysis_run_id FROM style_term_mentions "
            "WHERE analysis_run_id = ? ORDER BY scene_id, block_id, start_cp, id",
            (analysis_run_id,),
        ).fetchall()
        return tuple(TermMentionRecord(*row) for row in rows)
