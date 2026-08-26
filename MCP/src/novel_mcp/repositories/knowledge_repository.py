from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterKnowledgeEventRecord:
    id: int
    work_id: int
    character_id: int
    information_item_id: int
    episode_id: int
    knowledge_state: str
    note: str
    version: int
    created_at: str
    updated_at: str


_COLUMNS = (
    "id, work_id, character_id, information_item_id, episode_id, "
    "knowledge_state, note, version, created_at, updated_at"
)


class KnowledgeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def get(
        self,
        *,
        work_id: int,
        character_id: int,
        information_item_id: int,
        episode_id: int,
    ) -> CharacterKnowledgeEventRecord | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM character_knowledge_events "
            "WHERE work_id = ? AND character_id = ? AND information_item_id = ? "
            "AND episode_id = ?",
            (work_id, character_id, information_item_id, episode_id),
        ).fetchone()
        return None if row is None else CharacterKnowledgeEventRecord(*row)

    def create(self, *, work_id: int, fields: Mapping[str, object]) -> int:
        columns = ("work_id", *fields.keys())
        values = (work_id, *fields.values())
        cursor = self._connection.execute(
            f"INSERT INTO character_knowledge_events ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in values)})",
            values,
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("knowledge event insert did not return an id")
        return cursor.lastrowid

    def update(
        self,
        *,
        work_id: int,
        character_id: int,
        information_item_id: int,
        episode_id: int,
        expected_version: int,
        fields: Mapping[str, object],
    ) -> bool:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        cursor = self._connection.execute(
            f"UPDATE character_knowledge_events SET {assignments}, "
            "updated_at = CURRENT_TIMESTAMP, version = version + 1 "
            "WHERE work_id = ? AND character_id = ? AND information_item_id = ? "
            "AND episode_id = ? AND version = ?",
            (
                *fields.values(),
                work_id,
                character_id,
                information_item_id,
                episode_id,
                expected_version,
            ),
        )
        return cursor.rowcount == 1

    def list_for_character(
        self, *, work_id: int, character_id: int
    ) -> tuple[CharacterKnowledgeEventRecord, ...]:
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM character_knowledge_events "
            "WHERE work_id = ? AND character_id = ? ORDER BY id",
            (work_id, character_id),
        ).fetchall()
        return tuple(CharacterKnowledgeEventRecord(*row) for row in rows)
