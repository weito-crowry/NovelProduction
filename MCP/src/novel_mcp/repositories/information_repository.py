from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InformationItemRecord:
    id: int
    work_id: int
    statement: str
    truth_status: str
    authoring_guard: str
    notes_json: str
    canon_status: str
    importance: int
    version: int
    created_at: str
    updated_at: str


_COLUMNS = (
    "id, work_id, statement, truth_status, authoring_guard, notes_json, "
    "canon_status, importance, version, created_at, updated_at"
)


class InformationRepository:
    def __init__(
        self, connection: sqlite3.Connection, *, force_fallback: bool = False
    ) -> None:
        self._connection = connection
        self._supports_trigram = not force_fallback and self._detect_trigram()
        self._last_strategy = "none"

    @property
    def last_strategy(self) -> str:
        return self._last_strategy

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def create(self, *, work_id: int, fields: Mapping[str, object]) -> int:
        columns = ("work_id", *fields.keys())
        values = (work_id, *fields.values())
        cursor = self._connection.execute(
            f"INSERT INTO information_items ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in values)})",
            values,
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("information insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, item_id: int) -> InformationItemRecord | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM information_items WHERE work_id = ? AND id = ?",
            (work_id, item_id),
        ).fetchone()
        return None if row is None else InformationItemRecord(*row)

    def get_work_id(self, item_id: int) -> int | None:
        row = self._connection.execute(
            "SELECT work_id FROM information_items WHERE id = ?", (item_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def update(
        self,
        *,
        work_id: int,
        item_id: int,
        expected_version: int,
        fields: Mapping[str, object],
    ) -> bool:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        cursor = self._connection.execute(
            f"UPDATE information_items SET {assignments}, "
            "updated_at = CURRENT_TIMESTAMP, version = version + 1 "
            "WHERE work_id = ? AND id = ? AND version = ?",
            (*fields.values(), work_id, item_id, expected_version),
        )
        return cursor.rowcount == 1

    def search(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[InformationItemRecord, ...]:
        if self._supports_trigram and len(query) >= 3:
            try:
                ids = self._fts_ids(work_id, query, limit)
                self._last_strategy = "fts5_trigram"
                return self._rows_by_ids(work_id, ids)
            except sqlite3.Error:
                pass
        self._last_strategy = "parameterized_like"
        pattern = _like_pattern(query)
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM information_items "
            "WHERE work_id = ? AND (statement LIKE ? ESCAPE '\\' "
            "OR authoring_guard LIKE ? ESCAPE '\\') ORDER BY id LIMIT ?",
            (work_id, pattern, pattern, limit),
        ).fetchall()
        return tuple(InformationItemRecord(*row) for row in rows)

    def _detect_trigram(self) -> bool:
        try:
            self._connection.execute(
                "CREATE VIRTUAL TABLE temp.novel_mcp_information_probe "
                "USING fts5(content, tokenize='trigram')"
            )
            self._connection.execute("DROP TABLE temp.novel_mcp_information_probe")
        except sqlite3.Error:
            return False
        return True

    def _fts_ids(self, work_id: int, query: str, limit: int) -> tuple[int, ...]:
        table = "novel_mcp_information_fts"
        self._connection.execute(f"DROP TABLE IF EXISTS temp.{table}")
        self._connection.execute(
            f"CREATE VIRTUAL TABLE temp.{table} USING fts5("
            "row_id UNINDEXED, content, tokenize='trigram')"
        )
        try:
            self._connection.execute(
                f"INSERT INTO temp.{table}(row_id, content) "
                "SELECT id, statement || char(10) || authoring_guard "
                "FROM information_items WHERE work_id = ?",
                (work_id,),
            )
            phrase = '"' + query.replace('"', '""') + '"'
            rows = self._connection.execute(
                f"SELECT row_id FROM temp.{table} WHERE {table} MATCH ? "
                "ORDER BY CAST(row_id AS INTEGER) LIMIT ?",
                (phrase, limit),
            ).fetchall()
            return tuple(int(row[0]) for row in rows)
        finally:
            self._connection.execute(f"DROP TABLE temp.{table}")

    def _rows_by_ids(
        self, work_id: int, ids: tuple[int, ...]
    ) -> tuple[InformationItemRecord, ...]:
        if not ids:
            return ()
        placeholders = ", ".join("?" for _ in ids)
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM information_items "
            f"WHERE work_id = ? AND id IN ({placeholders}) ORDER BY id",
            (work_id, *ids),
        ).fetchall()
        return tuple(InformationItemRecord(*row) for row in rows)


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
