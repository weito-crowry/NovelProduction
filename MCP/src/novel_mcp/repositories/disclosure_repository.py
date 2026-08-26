from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReaderDisclosureRecord:
    id: int
    work_id: int
    information_item_id: int
    episode_id: int
    version: int
    created_at: str
    updated_at: str


class DisclosureRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def get(
        self, *, work_id: int, information_item_id: int
    ) -> ReaderDisclosureRecord | None:
        row = self._connection.execute(
            """
            SELECT id, work_id, information_item_id, episode_id, version,
                   created_at, updated_at
            FROM reader_disclosures
            WHERE work_id = ? AND information_item_id = ?
            """,
            (work_id, information_item_id),
        ).fetchone()
        return None if row is None else ReaderDisclosureRecord(*row)

    def create(self, *, work_id: int, information_item_id: int, episode_id: int) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO reader_disclosures (work_id, information_item_id, episode_id)
            VALUES (?, ?, ?)
            """,
            (work_id, information_item_id, episode_id),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError(
                "reader disclosure insert did not return an id"
            )
        return cursor.lastrowid

    def update(
        self,
        *,
        work_id: int,
        information_item_id: int,
        episode_id: int,
        expected_version: int,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE reader_disclosures
            SET episode_id = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
            WHERE work_id = ? AND information_item_id = ? AND version = ?
            """,
            (episode_id, work_id, information_item_id, expected_version),
        )
        return cursor.rowcount == 1
