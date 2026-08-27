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
    valid_from_episode_id: int | None
    valid_to_episode_id: int | None
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
        valid_from_episode_id: int | None,
        valid_to_episode_id: int | None,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO relationships
                (work_id, source_character_id, target_character_id,
                relationship_type, description, canon_status,
                valid_from_episode_id, valid_to_episode_id)
            VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)
            """,
            (
                work_id,
                source_character_id,
                target_character_id,
                relationship_type,
                description,
                valid_from_episode_id,
                valid_to_episode_id,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("relationship insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, relationship_id: int) -> RelationshipRecord | None:
        row = self._connection.execute(
            """
            SELECT id, work_id, source_character_id, target_character_id,
                   relationship_type, description, canon_status,
                   valid_from_episode_id, valid_to_episode_id, version,
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
                   relationship_type, description, canon_status,
                   valid_from_episode_id, valid_to_episode_id, version,
                   created_at, updated_at
            FROM relationships WHERE {condition} ORDER BY id LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return tuple(RelationshipRecord(*row) for row in rows)

    def find_same_definition(
        self,
        *,
        work_id: int,
        source_character_id: int,
        target_character_id: int,
        relationship_type: str,
        exclude_id: int | None = None,
    ) -> tuple[RelationshipRecord, ...]:
        condition = (
            "work_id = ? AND source_character_id = ? AND "
            "target_character_id = ? AND relationship_type = ?"
        )
        params: list[object] = [
            work_id,
            source_character_id,
            target_character_id,
            relationship_type,
        ]
        if exclude_id is not None:
            condition += " AND id != ?"
            params.append(exclude_id)
        rows = self._connection.execute(
            f"""
            SELECT id, work_id, source_character_id, target_character_id,
                   relationship_type, description, canon_status,
                   valid_from_episode_id, valid_to_episode_id, version,
                   created_at, updated_at
            FROM relationships WHERE {condition} ORDER BY id
            """,
            params,
        ).fetchall()
        return tuple(RelationshipRecord(*row) for row in rows)

    def list_all(self, *, work_id: int) -> tuple[RelationshipRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id, work_id, source_character_id, target_character_id,
                   relationship_type, description, canon_status,
                   valid_from_episode_id, valid_to_episode_id, version,
                   created_at, updated_at
            FROM relationships WHERE work_id = ? ORDER BY id
            """,
            (work_id,),
        ).fetchall()
        return tuple(RelationshipRecord(*row) for row in rows)
