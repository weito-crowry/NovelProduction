from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorldFactRecord:
    id: int
    statement: str
    valid_from: str | None
    valid_to: str | None
    created_at: str
    updated_at: str
    version: int


class WorldFactRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        work_id: int,
        fact_key: str,
        statement: str,
        valid_from: str | None,
        valid_to: str | None,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO world_facts (
                work_id,
                fact_key,
                title,
                body,
                canon_status,
                valid_from,
                valid_to
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_id,
                fact_key,
                statement,
                statement,
                "draft",
                valid_from,
                valid_to,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("world fact insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, fact_id: int) -> WorldFactRecord | None:
        row = self._connection.execute(
            """
            SELECT id, body, valid_from, valid_to, created_at, updated_at, version
            FROM world_facts
            WHERE work_id = ? AND id = ?
            """,
            (work_id, fact_id),
        ).fetchone()
        if row is None:
            return None
        return WorldFactRecord(*row)

    def update_statement(
        self,
        *,
        work_id: int,
        fact_id: int,
        expected_version: int,
        statement: str,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE world_facts
            SET
                title = ?,
                body = ?,
                updated_at = CURRENT_TIMESTAMP,
                version = version + 1
            WHERE work_id = ? AND id = ? AND version = ?
            """,
            (statement, statement, work_id, fact_id, expected_version),
        )
        return cursor.rowcount == 1

    def search(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[WorldFactRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id, body, valid_from, valid_to, created_at, updated_at, version
            FROM world_facts
            WHERE work_id = ? AND instr(body, ?) > 0
            ORDER BY id
            LIMIT ?
            """,
            (work_id, query, limit),
        ).fetchall()
        return tuple(WorldFactRecord(*row) for row in rows)
