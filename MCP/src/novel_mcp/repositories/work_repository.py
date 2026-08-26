from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from novel_mcp.errors import VersionConflictError


@dataclass(frozen=True, slots=True)
class WorkRecord:
    id: int
    slug: str
    title: str
    description: str | None
    created_at: str
    updated_at: str
    version: int


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
            SELECT id, slug, title, description, created_at, updated_at, version
            FROM works
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return WorkRecord(*row)

    def update(self, expected_version: int, title: str) -> WorkRecord:
        current = self.get()
        if current is None:
            raise VersionConflictError("VERSION_CONFLICT")
        cursor = self._connection.execute(
            """
            UPDATE works
            SET title = ?, updated_at = CURRENT_TIMESTAMP, version = version + 1
            WHERE id = ? AND version = ?
            """,
            (title, current.id, expected_version),
        )
        if cursor.rowcount == 0:
            raise VersionConflictError("VERSION_CONFLICT")
        updated = self.get()
        if updated is None:
            raise VersionConflictError("VERSION_CONFLICT")
        return updated

    def create(self, *, slug: str, title: str, description: str | None) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO works (slug, title, description)
            VALUES (?, ?, ?)
            """,
            (slug, title, description),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("work insert did not return an id")
        return cursor.lastrowid
