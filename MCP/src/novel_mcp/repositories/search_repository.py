from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from novel_mcp.repositories.character_repository import CharacterRecord
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
    """Search canonical rows with an ephemeral trigram index when available."""

    def __init__(
        self, connection: sqlite3.Connection, *, force_fallback: bool = False
    ) -> None:
        self._connection = connection
        self._supports_trigram = not force_fallback and self._detect_trigram()
        self._last_strategy = "none"

    @property
    def supports_trigram(self) -> bool:
        return self._supports_trigram

    @property
    def last_strategy(self) -> str:
        return self._last_strategy

    def search_world_facts(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[WorldFactRecord, ...]:
        if self._supports_trigram and len(query) >= 3:
            try:
                ids = self._fts_ids(
                    "world_facts",
                    "title || char(10) || statement",
                    work_id,
                    query,
                    limit,
                )
                self._last_strategy = "fts5_trigram"
                return self._world_rows_by_ids(work_id, ids)
            except sqlite3.Error:
                pass
        self._last_strategy = "parameterized_like"
        pattern = _like_pattern(query)
        rows = self._connection.execute(
            """
            SELECT id, work_id, topic_key, category, title, statement, details_json,
                   valid_from, valid_to, canon_status, importance, version,
                   created_at, updated_at
            FROM world_facts
            WHERE work_id = ?
              AND (title LIKE ? ESCAPE '\\' OR statement LIKE ? ESCAPE '\\')
            ORDER BY id LIMIT ?
            """,
            (work_id, pattern, pattern, limit),
        ).fetchall()
        return tuple(WorldFactRecord(*row) for row in rows)

    def search_characters(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[CharacterRecord, ...]:
        if self._supports_trigram and len(query) >= 3:
            try:
                ids = self._fts_ids(
                    "characters",
                    "display_name || char(10) || description",
                    work_id,
                    query,
                    limit,
                )
                self._last_strategy = "fts5_trigram"
                return self._character_rows_by_ids(work_id, ids)
            except sqlite3.Error:
                pass
        self._last_strategy = "parameterized_like"
        pattern = _like_pattern(query)
        rows = self._connection.execute(
            """
            SELECT id, work_id, character_key, display_name, entity_type, description,
                   birth_date, death_date, physical_description, occupation,
                   core_beliefs, goals, fears, personality, speech_style,
                   ai_attitude, genetic_modification_attitude, private_notes,
                   profile_json, canon_status, version, created_at, updated_at
            FROM characters
            WHERE work_id = ?
              AND (display_name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')
            ORDER BY id LIMIT ?
            """,
            (work_id, pattern, pattern, limit),
        ).fetchall()
        return tuple(CharacterRecord(*row) for row in rows)

    def diagnose_world_facts(
        self, *, work_id: int, query: str, limit: int
    ) -> SearchDiagnostic:
        rows = self.search_world_facts(work_id=work_id, query=query, limit=limit)
        return SearchDiagnostic(rows, query, work_id, limit, self._last_strategy)

    def diagnose_characters(
        self, *, work_id: int, query: str, limit: int
    ) -> SearchDiagnostic:
        rows = self.search_characters(work_id=work_id, query=query, limit=limit)
        return SearchDiagnostic(rows, query, work_id, limit, self._last_strategy)

    def _detect_trigram(self) -> bool:
        try:
            self._connection.execute(
                "CREATE VIRTUAL TABLE temp.novel_mcp_trigram_probe "
                "USING fts5(content, tokenize='trigram')"
            )
            self._connection.execute("DROP TABLE temp.novel_mcp_trigram_probe")
        except sqlite3.Error:
            return False
        return True

    def _fts_ids(
        self, source_table: str, expression: str, work_id: int, query: str, limit: int
    ) -> tuple[int, ...]:
        fts_table = "novel_mcp_ephemeral_fts"
        owns_transaction = not self._connection.in_transaction
        self._connection.execute(f"DROP TABLE IF EXISTS temp.{fts_table}")
        self._connection.execute(
            f"CREATE VIRTUAL TABLE temp.{fts_table} USING fts5("
            "row_id UNINDEXED, content, tokenize='trigram')"
        )
        try:
            self._connection.execute(
                f"""
                INSERT INTO temp.{fts_table}(row_id, content)
                SELECT id, {expression} FROM {source_table} WHERE work_id = ?
                """,
                (work_id,),
            )
            phrase = '"' + query.replace('"', '""') + '"'
            rows = self._connection.execute(
                f"SELECT row_id FROM temp.{fts_table} WHERE {fts_table} MATCH ? "
                "ORDER BY CAST(row_id AS INTEGER) LIMIT ?",
                (phrase, limit),
            ).fetchall()
            return tuple(int(row[0]) for row in rows)
        finally:
            try:
                self._connection.execute(f"DROP TABLE temp.{fts_table}")
            finally:
                if owns_transaction and self._connection.in_transaction:
                    self._connection.commit()

    def _world_rows_by_ids(
        self, work_id: int, ids: tuple[int, ...]
    ) -> tuple[WorldFactRecord, ...]:
        if not ids:
            return ()
        placeholders = ", ".join("?" for _ in ids)
        rows = self._connection.execute(
            f"""
            SELECT id, work_id, topic_key, category, title, statement, details_json,
                   valid_from, valid_to, canon_status, importance, version,
                   created_at, updated_at
            FROM world_facts WHERE work_id = ? AND id IN ({placeholders}) ORDER BY id
            """,
            (work_id, *ids),
        ).fetchall()
        return tuple(WorldFactRecord(*row) for row in rows)

    def _character_rows_by_ids(
        self, work_id: int, ids: tuple[int, ...]
    ) -> tuple[CharacterRecord, ...]:
        if not ids:
            return ()
        placeholders = ", ".join("?" for _ in ids)
        rows = self._connection.execute(
            f"""
            SELECT id, work_id, character_key, display_name, entity_type, description,
                   birth_date, death_date, physical_description, occupation,
                   core_beliefs, goals, fears, personality, speech_style,
                   ai_attitude, genetic_modification_attitude, private_notes,
                   profile_json, canon_status, version, created_at, updated_at
            FROM characters WHERE work_id = ? AND id IN ({placeholders}) ORDER BY id
            """,
            (work_id, *ids),
        ).fetchall()
        return tuple(CharacterRecord(*row) for row in rows)


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
