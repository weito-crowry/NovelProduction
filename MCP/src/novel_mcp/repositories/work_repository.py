from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from novel_mcp.errors import VersionConflictError


@dataclass(frozen=True, slots=True)
class WorkRecord:
    id: int
    slug: str
    working_title: str
    genre: str
    premise: str
    themes_json: str
    description: str
    production_status: str
    created_at: str
    updated_at: str
    version: int

    @property
    def title(self) -> str:
        return self.working_title


class WorkRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def get(self) -> WorkRecord | None:
        row = self._connection.execute(
            """
            SELECT id, slug, working_title, genre, premise, themes_json, description,
                   production_status, created_at, updated_at, version
            FROM works ORDER BY id LIMIT 1
            """
        ).fetchone()
        return None if row is None else WorkRecord(*row)

    def update(
        self, *, expected_version: int, fields: Mapping[str, object]
    ) -> WorkRecord:
        if not fields:
            raise ValueError("work update fields must be non-empty")
        assignments = ", ".join(f"{column} = ?" for column in fields)
        cursor = self._connection.execute(
            f"""
            UPDATE works
            SET {assignments}, updated_at = CURRENT_TIMESTAMP, version = version + 1
            WHERE id = (SELECT id FROM works ORDER BY id LIMIT 1)
              AND version = ?
            """,
            (*fields.values(), expected_version),
        )
        if cursor.rowcount == 0:
            raise VersionConflictError("VERSION_CONFLICT")
        updated = self.get()
        if updated is None:
            raise VersionConflictError("VERSION_CONFLICT")
        return updated

    def create(
        self,
        *,
        slug: str,
        working_title: str,
        genre: str,
        premise: str,
        themes_json: str,
        description: str,
        production_status: str,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO works
                (slug, working_title, genre, premise, themes_json, description,
                 production_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                working_title,
                genre,
                premise,
                themes_json,
                description,
                production_status,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("work insert did not return an id")
        return cursor.lastrowid
