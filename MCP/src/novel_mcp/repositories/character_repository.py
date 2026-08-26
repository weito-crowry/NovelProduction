from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    id: int
    work_id: int
    character_key: str
    display_name: str
    entity_type: str
    description: str
    birth_date: str | None
    death_date: str | None
    physical_description: str
    occupation: str
    core_beliefs: str
    goals: str
    fears: str
    personality: str
    speech_style: str
    ai_attitude: str
    genetic_modification_attitude: str
    private_notes: str
    profile_json: str
    canon_status: str
    version: int
    created_at: str
    updated_at: str

    @property
    def name(self) -> str:
        return self.display_name

    @property
    def profile(self) -> str:
        return self.description


class CharacterRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def create(self, *, work_id: int, fields: dict[str, object]) -> int:
        columns = ", ".join(("work_id", *fields.keys()))
        placeholders = ", ".join("?" for _ in range(len(fields) + 1))
        cursor = self._connection.execute(
            f"INSERT INTO characters ({columns}) VALUES ({placeholders})",
            (work_id, *fields.values()),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("character insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, character_id: int) -> CharacterRecord | None:
        row = self._connection.execute(
            """
            SELECT id, work_id, character_key, display_name, entity_type, description,
                   birth_date, death_date, physical_description, occupation,
                   core_beliefs, goals, fears, personality, speech_style,
                   ai_attitude, genetic_modification_attitude, private_notes,
                   profile_json, canon_status, version, created_at, updated_at
            FROM characters WHERE work_id = ? AND id = ?
            """,
            (work_id, character_id),
        ).fetchone()
        return None if row is None else CharacterRecord(*row)

    def get_work_id(self, character_id: int) -> int | None:
        row = self._connection.execute(
            "SELECT work_id FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def search(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[CharacterRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id, work_id, character_key, display_name, entity_type, description,
                   birth_date, death_date, physical_description, occupation,
                   core_beliefs, goals, fears, personality, speech_style,
                   ai_attitude, genetic_modification_attitude, private_notes,
                   profile_json, canon_status, version, created_at, updated_at
            FROM characters
            WHERE work_id = ?
              AND (instr(display_name, ?) > 0 OR instr(description, ?) > 0)
            ORDER BY id LIMIT ?
            """,
            (work_id, query, query, limit),
        ).fetchall()
        return tuple(CharacterRecord(*row) for row in rows)
