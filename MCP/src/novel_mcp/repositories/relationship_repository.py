from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RelationshipRecord:
    id: int
    work_id: int
    source_character_id: int
    target_character_id: int
    relationship_type: str
    description: str
    canon_status: str
    version: int
    created_at: str
    updated_at: str

    @property
    def relation_type(self) -> str:
        return self.relationship_type

    @property
    def summary(self) -> str:
        return self.description


class RelationshipRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def create(
        self,
        *,
        work_id: int,
        source_character_id: int,
        target_character_id: int,
        relationship_type: str,
        description: str,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO relationships
                (work_id, source_character_id, target_character_id,
                 relationship_type, description, canon_status)
            VALUES (?, ?, ?, ?, ?, 'draft')
            """,
            (
                work_id,
                source_character_id,
                target_character_id,
                relationship_type,
                description,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("relationship insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, relationship_id: int) -> RelationshipRecord | None:
        row = self._connection.execute(
            """
            SELECT id, work_id, source_character_id, target_character_id,
                   relationship_type, description, canon_status, version,
                   created_at, updated_at
            FROM relationships WHERE work_id = ? AND id = ?
            """,
            (work_id, relationship_id),
        ).fetchone()
        return None if row is None else RelationshipRecord(*row)

    def search(
        self, *, work_id: int, character_id: int | None, limit: int
    ) -> tuple[RelationshipRecord, ...]:
        condition = "work_id = ?"
        params: list[object] = [work_id]
        if character_id is not None:
            condition += " AND (source_character_id = ? OR target_character_id = ?)"
            params.extend((character_id, character_id))
        rows = self._connection.execute(
            f"""
            SELECT id, work_id, source_character_id, target_character_id,
                   relationship_type, description, canon_status, version,
                   created_at, updated_at
            FROM relationships WHERE {condition} ORDER BY id LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return tuple(RelationshipRecord(*row) for row in rows)
