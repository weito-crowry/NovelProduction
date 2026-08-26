from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class CanonChange:
    entity_type: str
    entity_id: int
    action: str
    before_payload: Mapping[str, object]
    after_payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class CanonDecisionRecord:
    id: int
    summary: str
    reason: str
    changes: tuple[CanonChange, ...]


_ENTITY_COLUMNS = {
    "world_fact": (
        "world_facts",
        ("title", "body", "canon_status", "valid_from", "valid_to", "version"),
    ),
    "timeline_event": (
        "timeline_events",
        (
            "event_key",
            "title",
            "summary",
            "chronology_sort_key",
            "canon_status",
            "version",
        ),
    ),
    "character": (
        "characters",
        ("character_key", "display_name", "summary", "canon_status", "version"),
    ),
    "relationship": (
        "relationships",
        (
            "source_character_id",
            "target_character_id",
            "relationship_type",
            "summary",
            "canon_status",
            "version",
        ),
    ),
}


class CanonRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def get_entity(
        self, *, work_id: int, entity_type: str, entity_id: int
    ) -> dict[str, object] | None:
        table, columns = _ENTITY_COLUMNS[entity_type]
        row = self._connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE work_id = ? AND id = ?",
            (work_id, entity_id),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(columns, row, strict=True))

    def update_status(
        self,
        *,
        work_id: int,
        entity_type: str,
        entity_id: int,
        expected_version: int,
        target_status: str,
    ) -> bool:
        table, _ = _ENTITY_COLUMNS[entity_type]
        cursor = self._connection.execute(
            f"""UPDATE {table}
                SET canon_status = ?, updated_at = CURRENT_TIMESTAMP,
                    version = version + 1
                WHERE work_id = ? AND id = ? AND version = ?""",
            (target_status, work_id, entity_id, expected_version),
        )
        return cursor.rowcount == 1

    def update_content(
        self,
        *,
        work_id: int,
        entity_type: str,
        entity_id: int,
        expected_version: int,
        fields: Mapping[str, object],
    ) -> bool:
        table, columns = _ENTITY_COLUMNS[entity_type]
        allowed = set(columns) - {
            "canon_status",
            "version",
            "event_key",
            "character_key",
        }
        if not fields or not set(fields).issubset(allowed):
            return False
        assignments = ", ".join(f"{column} = ?" for column in fields)
        values = [fields[column] for column in fields]
        cursor = self._connection.execute(
            f"""UPDATE {table}
                SET {assignments}, updated_at = CURRENT_TIMESTAMP, version = version + 1
                WHERE work_id = ? AND id = ? AND version = ?""",
            (*values, work_id, entity_id, expected_version),
        )
        return cursor.rowcount == 1

    def insert_decision(
        self,
        *,
        work_id: int,
        summary: str,
        reason: str,
        changes: Sequence[CanonChange],
    ) -> int:
        cursor = self._connection.execute(
            """INSERT INTO canon_decisions
                (work_id, decision_key, summary, reason, decided_at)
                VALUES (?, ?, ?, ?, ?)""",
            (
                work_id,
                uuid4().hex,
                summary,
                reason,
                datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("canon decision insert did not return an id")
        decision_id = cursor.lastrowid
        for change in changes:
            self._connection.execute(
                """INSERT INTO canon_decision_changes
                    (canon_decision_id, entity_type, entity_id, action,
                     before_payload, after_payload)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    decision_id,
                    change.entity_type,
                    change.entity_id,
                    change.action,
                    json.dumps(
                        change.before_payload, ensure_ascii=False, sort_keys=True
                    ),
                    json.dumps(
                        change.after_payload, ensure_ascii=False, sort_keys=True
                    ),
                ),
            )
        return decision_id

    def get_decision(
        self, *, work_id: int, decision_id: int
    ) -> CanonDecisionRecord | None:
        row = self._connection.execute(
            """SELECT id, summary, reason FROM canon_decisions
               WHERE work_id = ? AND id = ?""",
            (work_id, decision_id),
        ).fetchone()
        if row is None:
            return None
        return self._record_from_row(row)

    def search_decisions(
        self, *, work_id: int, query: str, limit: int
    ) -> tuple[CanonDecisionRecord, ...]:
        rows = self._connection.execute(
            """SELECT id, summary, reason FROM canon_decisions
               WHERE work_id = ? AND (instr(summary, ?) > 0 OR instr(reason, ?) > 0)
               ORDER BY id LIMIT ?""",
            (work_id, query, query, limit),
        ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def _record_from_row(self, row: tuple[object, ...]) -> CanonDecisionRecord:
        changes = self._connection.execute(
            """SELECT entity_type, entity_id, action, before_payload, after_payload
               FROM canon_decision_changes WHERE canon_decision_id = ? ORDER BY id""",
            (row[0],),
        ).fetchall()
        return CanonDecisionRecord(
            id=cast(int, row[0]),
            summary=str(row[1]),
            reason=str(row[2]),
            changes=tuple(
                CanonChange(
                    entity_type=str(change[0]),
                    entity_id=int(change[1]),
                    action=str(change[2]),
                    before_payload=json.loads(change[3]),
                    after_payload=json.loads(change[4]),
                )
                for change in changes
            ),
        )
