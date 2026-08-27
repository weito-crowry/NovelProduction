from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EpisodeReferenceRecord:
    id: int
    work_id: int
    episode_id: int
    reference_type: str
    target_id: int
    role: str | None
    created_at: str


_TABLES = {
    "character": ("episode_characters", "character_id", True),
    "world_fact": ("episode_world_facts", "world_fact_id", False),
    "timeline_event": ("episode_timeline_events", "timeline_event_id", False),
    "information": ("episode_information", "information_item_id", False),
}


class EpisodeReferenceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def add(
        self,
        *,
        work_id: int,
        episode_id: int,
        reference_type: str,
        target_id: int,
        role: str | None,
    ) -> int:
        table, target_column, has_role = _TABLES[reference_type]
        columns = ["work_id", "episode_id", target_column]
        values: list[object] = [work_id, episode_id, target_id]
        if has_role:
            columns.append("role")
            values.append(role)
        cursor = self._connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in values)})",
            values,
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError(
                "episode reference insert did not return an id"
            )
        return cursor.lastrowid

    def remove(
        self,
        *,
        work_id: int,
        episode_id: int,
        reference_type: str,
        target_id: int,
    ) -> bool:
        table, target_column, _ = _TABLES[reference_type]
        cursor = self._connection.execute(
            f"DELETE FROM {table} WHERE work_id = ? AND episode_id = ? "
            f"AND {target_column} = ?",
            (work_id, episode_id, target_id),
        )
        return cursor.rowcount == 1

    def list(
        self,
        *,
        work_id: int,
        episode_id: int,
        reference_type: str | None,
    ) -> tuple[EpisodeReferenceRecord, ...]:
        types = (reference_type,) if reference_type is not None else tuple(_TABLES)
        records: list[EpisodeReferenceRecord] = []
        for current_type in types:
            table, target_column, has_role = _TABLES[current_type]
            role_column = ", role" if has_role else ", NULL"
            rows = self._connection.execute(
                f"SELECT id, work_id, episode_id, {target_column}{role_column}, "
                f"created_at FROM {table} WHERE work_id = ? AND episode_id = ? "
                "ORDER BY id",
                (work_id, episode_id),
            ).fetchall()
            records.extend(
                EpisodeReferenceRecord(
                    id=int(row[0]),
                    work_id=int(row[1]),
                    episode_id=int(row[2]),
                    reference_type=current_type,
                    target_id=int(row[3]),
                    role=None if row[4] is None else str(row[4]),
                    created_at=str(row[5]),
                )
                for row in rows
            )
        return tuple(records)

    @staticmethod
    def table_for(reference_type: str) -> tuple[str, str, bool]:
        return _TABLES[reference_type]
