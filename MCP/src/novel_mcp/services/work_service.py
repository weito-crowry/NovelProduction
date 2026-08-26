from __future__ import annotations

import sqlite3

from novel_mcp.errors import WorkNotFoundError
from novel_mcp.repositories.work_repository import WorkRecord, WorkRepository


class WorkService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = WorkRepository(connection)

    def get(self) -> WorkRecord:
        record = self._repository.get()
        if record is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return record

    def update(self, title: str, expected_version: int) -> WorkRecord:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("title must be non-empty")
        self._repository.begin_write()
        try:
            updated = self._repository.update(
                expected_version=expected_version,
                title=normalized_title,
            )
            self._repository.commit()
            return updated
        except Exception:
            self._repository.rollback()
            raise
