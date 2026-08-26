from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    id: int
    name: str
    profile: str
    created_at: str
    updated_at: str
    version: int


class CharacterRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self, *, work_id: int, character_key: str, name: str, profile: str
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO characters
                (work_id, character_key, display_name, summary, canon_status)
            VALUES (?, ?, ?, ?, 'draft')
            """,
            (work_id, character_key, name, profile),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("character insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, character_id: int) -> CharacterRecord | None:
        row = self._connection.execute(
            """
            SELECT id, display_name, summary, created_at, updated_at, version
            FROM characters
            WHERE work_id = ? AND id = ?
            """,
            (work_id, character_id),
        ).fetchone()
        return None if row is None else CharacterRecord(*row)

    def update(
        self,
        *,
        work_id: int,
        character_id: int,
        expected_version: int,
        name: str,
        profile: str,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE characters
            SET display_name = ?, summary = ?,
                updated_at = CURRENT_TIMESTAMP, version = version + 1
            WHERE work_id = ? AND id = ? AND version = ?
            """,
            (name, profile, work_id, character_id, expected_version),
        )
        return cursor.rowcount == 1

    def search(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[CharacterRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id, display_name, summary, created_at, updated_at, version
            FROM characters
            WHERE work_id = ?
              AND (instr(display_name, ?) > 0 OR instr(summary, ?) > 0)
            ORDER BY id
            LIMIT ?
            """,
            (work_id, query, query, limit),
        ).fetchall()
        return tuple(CharacterRecord(*row) for row in rows)
