from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorldFactRecord:
    id: int
    work_id: int
    topic_key: str
    category: str
    title: str
    statement: str
    details_json: str
    valid_from: str | None
    valid_to: str | None
    canon_status: str
    importance: int
    version: int
    created_at: str
    updated_at: str


class WorldFactRepository:
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
        topic_key: str,
        category: str,
        title: str,
        statement: str,
        details_json: str,
        valid_from: str | None,
        valid_to: str | None,
        importance: int,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO world_facts
                (work_id, topic_key, category, title, statement, details_json,
                 valid_from, valid_to, canon_status, importance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)
            """,
            (
                work_id,
                topic_key,
                category,
                title,
                statement,
                details_json,
                valid_from,
                valid_to,
                importance,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("world fact insert did not return an id")
        return cursor.lastrowid

    def get(self, *, work_id: int, fact_id: int) -> WorldFactRecord | None:
        row = self._connection.execute(
            """
            SELECT id, work_id, topic_key, category, title, statement, details_json,
                   valid_from, valid_to, canon_status, importance, version,
                   created_at, updated_at
            FROM world_facts WHERE work_id = ? AND id = ?
            """,
            (work_id, fact_id),
        ).fetchone()
        return None if row is None else WorldFactRecord(*row)

    def get_work_id(self, fact_id: int) -> int | None:
        row = self._connection.execute(
            "SELECT work_id FROM world_facts WHERE id = ?", (fact_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def list(
        self, *, work_id: int, limit: int, offset: int
    ) -> tuple[WorldFactRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id, work_id, topic_key, category, title, statement, details_json,
                   valid_from, valid_to, canon_status, importance, version,
                   created_at, updated_at
            FROM world_facts
            WHERE work_id = ?
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            (work_id, limit, offset),
        ).fetchall()
        return tuple(WorldFactRecord(*row) for row in rows)

    def search(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[WorldFactRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id, work_id, topic_key, category, title, statement, details_json,
                   valid_from, valid_to, canon_status, importance, version,
                   created_at, updated_at
            FROM world_facts
            WHERE work_id = ? AND (instr(title, ?) > 0 OR instr(statement, ?) > 0)
            ORDER BY id LIMIT ?
            """,
            (work_id, query, query, limit),
        ).fetchall()
        return tuple(WorldFactRecord(*row) for row in rows)
