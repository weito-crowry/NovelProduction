from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DraftRecord:
    id: int
    work_id: int
    episode_id: int
    revision: int
    parent_draft_id: int | None
    document_json: str
    source_agent: str | None
    change_summary: str
    created_at: str


@dataclass(frozen=True, slots=True)
class DraftMetadata:
    id: int
    episode_id: int
    revision: int
    parent_draft_id: int | None
    source_agent: str | None
    change_summary: str
    created_at: str


_RECORD_COLUMNS = (
    "id, work_id, episode_id, revision, parent_draft_id, document_json, "
    "source_agent, change_summary, created_at"
)
_METADATA_COLUMNS = (
    "id, episode_id, revision, parent_draft_id, source_agent, change_summary, "
    "created_at"
)


class DraftRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def latest(self, *, work_id: int, episode_id: int) -> DraftRecord | None:
        row = self._connection.execute(
            f"SELECT {_RECORD_COLUMNS} FROM drafts "
            "WHERE work_id = ? AND episode_id = ? ORDER BY revision DESC LIMIT 1",
            (work_id, episode_id),
        ).fetchone()
        return None if row is None else DraftRecord(*row)

    def get(
        self, *, work_id: int, episode_id: int, revision: int | None
    ) -> DraftRecord | None:
        if revision is None:
            return self.latest(work_id=work_id, episode_id=episode_id)
        row = self._connection.execute(
            f"SELECT {_RECORD_COLUMNS} FROM drafts "
            "WHERE work_id = ? AND episode_id = ? AND revision = ?",
            (work_id, episode_id, revision),
        ).fetchone()
        return None if row is None else DraftRecord(*row)

    def insert(
        self,
        *,
        work_id: int,
        episode_id: int,
        revision: int,
        parent_draft_id: int | None,
        document_json: str,
        source_agent: str | None,
        change_summary: str,
    ) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO drafts
                (work_id, episode_id, revision, parent_draft_id, document_json,
                 source_agent, change_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_id,
                episode_id,
                revision,
                parent_draft_id,
                document_json,
                source_agent,
                change_summary,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("draft insert did not return an id")
        return cursor.lastrowid

    def history(
        self, *, work_id: int, episode_id: int, limit: int
    ) -> tuple[DraftMetadata, ...]:
        rows = self._connection.execute(
            f"SELECT {_METADATA_COLUMNS} FROM drafts "
            "WHERE work_id = ? AND episode_id = ? "
            "ORDER BY revision DESC LIMIT ?",
            (work_id, episode_id, limit),
        ).fetchall()
        return tuple(DraftMetadata(*row) for row in reversed(rows))
