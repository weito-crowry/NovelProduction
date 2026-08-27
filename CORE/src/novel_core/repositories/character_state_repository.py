from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterStateRecord:
    id: int
    work_id: int
    character_id: int
    episode_id: int
    physical_state: str
    emotional_state: str
    beliefs_json: str
    location_world_fact_id: int | None
    state_json: str
    version: int
    created_at: str
    updated_at: str


_COLUMNS = (
    "id, work_id, character_id, episode_id, physical_state, emotional_state, "
    "beliefs_json, location_world_fact_id, state_json, version, created_at, updated_at"
)


class CharacterStateRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def get(
        self, *, work_id: int, character_id: int, episode_id: int
    ) -> CharacterStateRecord | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM character_states "
            "WHERE work_id = ? AND character_id = ? AND episode_id = ?",
            (work_id, character_id, episode_id),
        ).fetchone()
        return None if row is None else CharacterStateRecord(*row)

    def create(self, *, work_id: int, fields: Mapping[str, object]) -> int:
        columns = ("work_id", *fields.keys())
        values = (work_id, *fields.values())
        cursor = self._connection.execute(
            f"INSERT INTO character_states ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in values)})",
            values,
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("character state insert did not return an id")
        return cursor.lastrowid

    def update(
        self,
        *,
        work_id: int,
        character_id: int,
        episode_id: int,
        expected_version: int,
        fields: Mapping[str, object],
    ) -> bool:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        cursor = self._connection.execute(
            f"UPDATE character_states SET {assignments}, "
            "updated_at = CURRENT_TIMESTAMP, version = version + 1 "
            "WHERE work_id = ? AND character_id = ? AND episode_id = ? AND version = ?",
            (*fields.values(), work_id, character_id, episode_id, expected_version),
        )
        return cursor.rowcount == 1

    def history(
        self, *, work_id: int, character_id: int
    ) -> tuple[CharacterStateRecord, ...]:
        rows = self._connection.execute(
            f"SELECT s.{_COLUMNS.replace(', ', ', s.')} "
            "FROM character_states AS s "
            "JOIN episodes AS e ON e.work_id = s.work_id AND e.id = s.episode_id "
            "JOIN chapters AS c ON c.work_id = e.work_id AND c.id = e.chapter_id "
            "WHERE s.work_id = ? AND s.character_id = ? "
            "ORDER BY c.position, e.position, s.id",
            (work_id, character_id),
        ).fetchall()
        return tuple(CharacterStateRecord(*row) for row in rows)

    def effective(
        self, *, work_id: int, character_id: int, episode_id: int
    ) -> CharacterStateRecord | None:
        row = self._connection.execute(
            f"SELECT s.{_COLUMNS.replace(', ', ', s.')} "
            "FROM character_states AS s "
            "JOIN episodes AS e ON e.work_id = s.work_id AND e.id = s.episode_id "
            "JOIN chapters AS c ON c.work_id = e.work_id AND c.id = e.chapter_id "
            "JOIN episodes AS target_e ON target_e.work_id = ? AND target_e.id = ? "
            "JOIN chapters AS target_c ON target_c.work_id = target_e.work_id "
            "AND target_c.id = target_e.chapter_id "
            "WHERE s.work_id = ? AND s.character_id = ? "
            "AND (c.position < target_c.position OR "
            "(c.position = target_c.position AND e.position <= target_e.position)) "
            "ORDER BY c.position DESC, e.position DESC, s.id DESC LIMIT 1",
            (work_id, episode_id, work_id, character_id),
        ).fetchone()
        return None if row is None else CharacterStateRecord(*row)
