from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from novel_mcp.repositories.character_repository import (
    CharacterRecord,
)
from novel_mcp.repositories.world_fact_repository import WorldFactRecord


@dataclass(frozen=True, slots=True)
class SearchDiagnostic:
    rows: tuple[WorldFactRecord | CharacterRecord, ...]
    query: str
    work_id: int
    limit: int
    strategy: str

    @property
    def match_count(self) -> int:
        return len(self.rows)


class SearchRepository:
    """Read canonical searchable rows using a safe SQLite text fallback."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def search_world_facts(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[WorldFactRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id, body, valid_from, valid_to, created_at, updated_at, version
            FROM world_facts
            WHERE work_id = ? AND body LIKE ? ESCAPE '\\'
            ORDER BY id ASC
            LIMIT ?
            """,
            (work_id, _like_pattern(query), limit),
        ).fetchall()
        return tuple(WorldFactRecord(*row) for row in rows)

    def search_characters(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[CharacterRecord, ...]:
        pattern = _like_pattern(query)
        rows = self._connection.execute(
            """
            SELECT id, display_name, summary, created_at, updated_at, version
            FROM characters
            WHERE work_id = ?
              AND (display_name LIKE ? ESCAPE '\\'
                   OR summary LIKE ? ESCAPE '\\')
            ORDER BY id ASC
            LIMIT ?
            """,
            (work_id, pattern, pattern, limit),
        ).fetchall()
        return tuple(CharacterRecord(*row) for row in rows)

    def diagnose_world_facts(
        self, *, work_id: int, query: str, limit: int
    ) -> SearchDiagnostic:
        rows = self.search_world_facts(work_id=work_id, query=query, limit=limit)
        return SearchDiagnostic(rows, query, work_id, limit, "parameterized_like")

    def diagnose_characters(
        self, *, work_id: int, query: str, limit: int
    ) -> SearchDiagnostic:
        rows = self.search_characters(work_id=work_id, query=query, limit=limit)
        return SearchDiagnostic(rows, query, work_id, limit, "parameterized_like")


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
