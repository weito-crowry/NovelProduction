from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimelineEventRecord:
    id: int
    event_key: str
    title: str
    chronology_sort_key: str
    canon_status: str
    participants: tuple[tuple[str, str], ...]
    created_at: str
    updated_at: str
    version: int


@dataclass(frozen=True, slots=True)
class TimelineRelationRecord:
    id: int
    work_id: int
    source_event_id: int
    target_event_id: int
    relation_type: str
    version: int


class TimelineRepository:
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
        event_key: str,
        title: str,
        chronology_sort_key: str,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO timeline_events (
                work_id, event_key, title, summary, chronology_sort_key, canon_status
            ) VALUES (?, ?, ?, ?, ?, 'draft')
            """,
            (work_id, event_key, title, title, chronology_sort_key),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("timeline event insert did not return an id")
        return cursor.lastrowid

    def add_participant(self, *, event_id: int, label: str, role: str) -> None:
        self._connection.execute(
            """
            INSERT INTO timeline_event_participants
                (timeline_event_id, participant_label, role)
            VALUES (?, ?, ?)
            """,
            (event_id, label, role),
        )

    def replace_participants(
        self, *, event_id: int, participants: tuple[tuple[str, str], ...]
    ) -> None:
        self._connection.execute(
            "DELETE FROM timeline_event_participants WHERE timeline_event_id = ?",
            (event_id,),
        )
        for label, role in participants:
            self.add_participant(event_id=event_id, label=label, role=role)

    def get(self, *, work_id: int, event_id: int) -> TimelineEventRecord | None:
        row = self._connection.execute(
            """
            SELECT id, event_key, title, chronology_sort_key, canon_status,
                   created_at, updated_at, version
            FROM timeline_events
            WHERE work_id = ? AND id = ?
            """,
            (work_id, event_id),
        ).fetchone()
        if row is None:
            return None
        participants = tuple(
            self._connection.execute(
                """
                SELECT participant_label, role
                FROM timeline_event_participants
                WHERE timeline_event_id = ?
                ORDER BY id
                """,
                (event_id,),
            ).fetchall()
        )
        return TimelineEventRecord(
            id=row[0],
            event_key=row[1],
            title=row[2],
            chronology_sort_key=row[3],
            canon_status=row[4],
            participants=participants,
            created_at=row[5],
            updated_at=row[6],
            version=row[7],
        )

    def get_work_id(self, event_id: int) -> int | None:
        row = self._connection.execute(
            "SELECT work_id FROM timeline_events WHERE id = ?", (event_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def update(
        self,
        *,
        work_id: int,
        event_id: int,
        expected_version: int,
        title: str | None,
        chronology_sort_key: str | None,
    ) -> bool:
        current = self._connection.execute(
            """
            SELECT title, chronology_sort_key
            FROM timeline_events
            WHERE work_id = ? AND id = ?
            """,
            (work_id, event_id),
        ).fetchone()
        if current is None:
            return False
        cursor = self._connection.execute(
            """
            UPDATE timeline_events
            SET title = ?, summary = ?, chronology_sort_key = ?,
                updated_at = CURRENT_TIMESTAMP, version = version + 1
            WHERE work_id = ? AND id = ? AND version = ?
            """,
            (
                title if title is not None else current[0],
                title if title is not None else current[0],
                chronology_sort_key if chronology_sort_key is not None else current[1],
                work_id,
                event_id,
                expected_version,
            ),
        )
        return cursor.rowcount == 1

    def search(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[TimelineEventRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id FROM timeline_events
            WHERE work_id = ? AND (instr(title, ?) > 0 OR instr(summary, ?) > 0)
            ORDER BY chronology_sort_key, id LIMIT ?
            """,
            (work_id, query, query, limit),
        ).fetchall()
        return tuple(
            record
            for (event_id,) in rows
            if (record := self.get(work_id=work_id, event_id=event_id)) is not None
        )

    def range(
        self, *, work_id: int, start: str, end: str, limit: int
    ) -> tuple[TimelineEventRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id FROM timeline_events
            WHERE work_id = ? AND chronology_sort_key >= ?
              AND chronology_sort_key <= ?
            ORDER BY chronology_sort_key, id LIMIT ?
            """,
            (work_id, start, end, limit),
        ).fetchall()
        return tuple(
            record
            for (event_id,) in rows
            if (record := self.get(work_id=work_id, event_id=event_id)) is not None
        )

    def create_relation(
        self,
        *,
        work_id: int,
        source_event_id: int,
        target_event_id: int,
        relation_type: str,
    ) -> TimelineRelationRecord:
        cursor = self._connection.execute(
            """
            INSERT INTO timeline_event_relations
                (work_id, source_event_id, target_event_id, relation_type)
            VALUES (?, ?, ?, ?)
            """,
            (work_id, source_event_id, target_event_id, relation_type),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError(
                "timeline relation insert did not return an id"
            )
        row = self._connection.execute(
            """
            SELECT id, work_id, source_event_id, target_event_id, relation_type, version
            FROM timeline_event_relations WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise sqlite3.IntegrityError("timeline relation creation failed")
        return TimelineRelationRecord(*row)
