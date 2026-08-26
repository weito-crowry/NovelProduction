from __future__ import annotations

import sqlite3
from datetime import date
from uuid import uuid4

from novel_mcp.errors import (
    VersionConflictError,
    WorkNotFoundError,
    WorldFactNotFoundError,
)
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.repositories.world_fact_repository import (
    WorldFactRecord,
    WorldFactRepository,
)


class WorldFactService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._work_repository = WorkRepository(connection)
        self._repository = WorldFactRepository(connection)

    def create(
        self,
        statement: str,
        valid_from: str | None,
        valid_to: str | None,
    ) -> WorldFactRecord:
        normalized_statement = statement.strip()
        if not normalized_statement:
            raise ValueError("statement must be non-empty")
        normalized_valid_from, normalized_valid_to = self._validate_temporal_bounds(
            valid_from, valid_to
        )
        work_id = self._get_work_id()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            fact_id = self._repository.create(
                work_id=work_id,
                fact_key=uuid4().hex,
                statement=normalized_statement,
                valid_from=normalized_valid_from,
                valid_to=normalized_valid_to,
            )
            created = self._repository.get(work_id=work_id, fact_id=fact_id)
            if created is None:
                raise sqlite3.IntegrityError("world fact creation failed")
            self._connection.commit()
            return created
        except Exception:
            self._connection.rollback()
            raise

    def get(self, fact_id: int) -> WorldFactRecord:
        record = self._repository.get(work_id=self._get_work_id(), fact_id=fact_id)
        if record is None:
            raise WorldFactNotFoundError("NOT_FOUND")
        return record

    def update(
        self, fact_id: int, statement: str, expected_version: int
    ) -> WorldFactRecord:
        normalized_statement = statement.strip()
        if not normalized_statement:
            raise ValueError("statement must be non-empty")
        work_id = self._get_work_id()
        if self._repository.get(work_id=work_id, fact_id=fact_id) is None:
            raise WorldFactNotFoundError("NOT_FOUND")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            updated = self._repository.update_statement(
                work_id=work_id,
                fact_id=fact_id,
                expected_version=expected_version,
                statement=normalized_statement,
            )
            if not updated:
                raise VersionConflictError("VERSION_CONFLICT")
            record = self._repository.get(work_id=work_id, fact_id=fact_id)
            if record is None:
                raise WorldFactNotFoundError("NOT_FOUND")
            self._connection.commit()
            return record
        except Exception:
            self._connection.rollback()
            raise

    def search(self, query: str, limit: int) -> tuple[WorldFactRecord, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0:
            return ()
        return self._repository.search(
            work_id=self._get_work_id(),
            query=normalized_query,
            limit=limit,
        )

    def _get_work_id(self) -> int:
        record = self._work_repository.get()
        if record is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return record.id

    def _validate_temporal_bounds(
        self,
        valid_from: str | None,
        valid_to: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_valid_from = self._normalize_date(
            valid_from, field_name="valid_from"
        )
        normalized_valid_to = self._normalize_date(valid_to, field_name="valid_to")
        if (
            normalized_valid_from is not None
            and normalized_valid_to is not None
            and normalized_valid_from > normalized_valid_to
        ):
            raise ValueError("valid_to must be on or after valid_from")
        return normalized_valid_from, normalized_valid_to

    def _normalize_date(self, value: str | None, *, field_name: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return date.fromisoformat(normalized).isoformat()
        except ValueError as exc:
            raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc
