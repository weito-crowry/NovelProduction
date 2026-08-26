from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RelationshipRecord:
    id: int
    source_character_id: int
    target_character_id: int
    relation_type: str
    created_at: str
    updated_at: str
    version: int


class RelationshipRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        work_id: int,
        source_character_id: int,
        target_character_id: int,
        relation_type: str,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO relationships
                (work_id, source_character_id, target_character_id,
                 relationship_type, summary, canon_status)
            VALUES (?, ?, ?, ?, '', 'draft')
            """,
            (
                work_id,
                source_character_id,
                target_character_id,
                relation_type,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("relationship insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, relationship_id: int) -> RelationshipRecord | None:
        row = self._connection.execute(
            """
            SELECT id, source_character_id, target_character_id,
                   relationship_type, created_at, updated_at, version
            FROM relationships
            WHERE work_id = ? AND id = ?
            """,
            (work_id, relationship_id),
        ).fetchone()
        return None if row is None else RelationshipRecord(*row)

    def update(
        self,
        *,
        work_id: int,
        relationship_id: int,
        expected_version: int,
        relation_type: str,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE relationships
            SET relationship_type = ?, updated_at = CURRENT_TIMESTAMP,
                version = version + 1
            WHERE work_id = ? AND id = ? AND version = ?
            """,
            (relation_type, work_id, relationship_id, expected_version),
        )
        return cursor.rowcount == 1

    def search(
        self, *, work_id: int, character_id: int | None, limit: int
    ) -> tuple[RelationshipRecord, ...]:
        if character_id is None:
            rows = self._connection.execute(
                """
                SELECT id, source_character_id, target_character_id,
                       relationship_type, created_at, updated_at, version
                FROM relationships
                WHERE work_id = ?
                ORDER BY id
                LIMIT ?
                """,
                (work_id, limit),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT id, source_character_id, target_character_id,
                       relationship_type, created_at, updated_at, version
                FROM relationships
                WHERE work_id = ?
                  AND (source_character_id = ? OR target_character_id = ?)
                ORDER BY id
                LIMIT ?
                """,
                (work_id, character_id, character_id, limit),
            ).fetchall()
        return tuple(RelationshipRecord(*row) for row in rows)
