from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class TimelineParticipantRecord:
    event_id: int
    character_id: int
    role: str


@dataclass(frozen=True, slots=True)
class TimelineEventRecord:
    id: int
    work_id: int
    event_key: str
    time_start: str | None
    time_end: str | None
    date_precision: str
    date_display: str
    title: str
    description: str
    category: str
    location_world_fact_id: int | None
    cause_summary: str
    consequence_summary: str
    canon_status: str
    importance: int
    version: int
    created_at: str
    updated_at: str
    participants: tuple[TimelineParticipantRecord, ...]

    @property
    def chronology_sort_key(self) -> str:
        return self.time_start or ""


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

    def create(self, *, work_id: int, fields: dict[str, object]) -> int:
        columns = ", ".join(("work_id", *fields.keys()))
        placeholders = ", ".join("?" for _ in range(len(fields) + 1))
        cursor = self._connection.execute(
            f"INSERT INTO timeline_events ({columns}) VALUES ({placeholders})",
            (work_id, *fields.values()),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("timeline event insert did not return an id")
        return cursor.lastrowid

    def add_participant(self, *, event_id: int, character_id: int, role: str) -> None:
        self._connection.execute(
            """
            INSERT INTO timeline_event_participants (event_id, character_id, role)
            VALUES (?, ?, ?)
            """,
            (event_id, character_id, role),
        )

    def replace_participants(
        self, *, event_id: int, participants: tuple[tuple[int, str], ...]
    ) -> None:
        self._connection.execute(
            "DELETE FROM timeline_event_participants WHERE event_id = ?", (event_id,)
        )
        for character_id, role in participants:
            self.add_participant(
                event_id=event_id, character_id=character_id, role=role
            )

    def get(self, *, work_id: int, event_id: int) -> TimelineEventRecord | None:
        row = self._connection.execute(
            """
            SELECT id, work_id, event_key, time_start, time_end, date_precision,
                   date_display, title, description, category,
                   location_world_fact_id, cause_summary, consequence_summary,
                   canon_status, importance, version, created_at, updated_at
            FROM timeline_events WHERE work_id = ? AND id = ?
            """,
            (work_id, event_id),
        ).fetchone()
        if row is None:
            return None
        participants = tuple(
            TimelineParticipantRecord(*participant)
            for participant in self._connection.execute(
                """
                SELECT event_id, character_id, role
                FROM timeline_event_participants
                WHERE event_id = ? ORDER BY id
                """,
                (event_id,),
            ).fetchall()
        )
        return TimelineEventRecord(
            id=cast(int, row[0]),
            work_id=cast(int, row[1]),
            event_key=cast(str, row[2]),
            time_start=cast(str | None, row[3]),
            time_end=cast(str | None, row[4]),
            date_precision=cast(str, row[5]),
            date_display=cast(str, row[6]),
            title=cast(str, row[7]),
            description=cast(str, row[8]),
            category=cast(str, row[9]),
            location_world_fact_id=cast(int | None, row[10]),
            cause_summary=cast(str, row[11]),
            consequence_summary=cast(str, row[12]),
            canon_status=cast(str, row[13]),
            importance=cast(int, row[14]),
            version=cast(int, row[15]),
            created_at=cast(str, row[16]),
            updated_at=cast(str, row[17]),
            participants=participants,
        )

    def get_work_id(self, event_id: int) -> int | None:
        row = self._connection.execute(
            "SELECT work_id FROM timeline_events WHERE id = ?", (event_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def search(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[TimelineEventRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT id FROM timeline_events
            WHERE work_id = ? AND (instr(title, ?) > 0 OR instr(description, ?) > 0)
            ORDER BY COALESCE(time_start, '9999-12-31'), id LIMIT ?
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
            WHERE work_id = ? AND time_start IS NOT NULL
              AND time_start <= ? AND time_end >= ?
            ORDER BY time_start, id LIMIT ?
            """,
            (work_id, end, start, limit),
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
