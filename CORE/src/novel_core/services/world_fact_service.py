from __future__ import annotations

import json
import sqlite3
from datetime import date
from uuid import uuid4

from novel_core.errors import (
    CanonEntityNotFoundError,
    ValidationError,
    WorkNotFoundError,
    WorldFactNotFoundError,
)
from novel_core.repositories.work_repository import WorkRepository
from novel_core.repositories.world_fact_repository import (
    WorldFactRecord,
    WorldFactRepository,
)
from novel_core.services.canon_service import CanonService
from novel_core.services.search_service import MAX_SEARCH_LIMIT


class WorldFactService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._work_repository = WorkRepository(connection)
        self._repository = WorldFactRepository(connection)
        self._canon_service = CanonService(connection)

    def create(
        self,
        statement: str,
        valid_from: str | None = None,
        valid_to: str | None = None,
        *,
        topic_key: str | None = None,
        category: str = "general",
        title: str | None = None,
        details_json: str = "{}",
        importance: int = 0,
    ) -> WorldFactRecord:
        normalized_statement = self._required_text(statement, "statement")
        normalized_topic = self._required_text(topic_key or uuid4().hex, "topic_key")
        normalized_category = self._required_text(category, "category")
        normalized_title = self._required_text(title or normalized_statement, "title")
        normalized_details = self._json_text(details_json)
        normalized_valid_from, normalized_valid_to = self._validate_temporal_bounds(
            valid_from, valid_to
        )
        if not isinstance(importance, int) or importance < 0:
            raise ValidationError("importance must be non-negative", field="importance")
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            fact_id = self._repository.create(
                work_id=work_id,
                topic_key=normalized_topic,
                category=normalized_category,
                title=normalized_title,
                statement=normalized_statement,
                details_json=normalized_details,
                valid_from=normalized_valid_from,
                valid_to=normalized_valid_to,
                importance=importance,
            )
            created = self._repository.get(work_id=work_id, fact_id=fact_id)
            if created is None:
                raise sqlite3.IntegrityError("world fact creation failed")
            self._repository.commit()
            return created
        except Exception:
            self._repository.rollback()
            raise

    def get(self, fact_id: int) -> WorldFactRecord:
        record = self._repository.get(work_id=self._work_id(), fact_id=fact_id)
        if record is None:
            raise WorldFactNotFoundError("NOT_FOUND")
        return record

    def update(
        self,
        fact_id: int,
        statement: str,
        expected_version: int,
        reason: str | None = None,
        *,
        topic_key: str | None = None,
        category: str | None = None,
        title: str | None = None,
        details_json: str | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        importance: int | None = None,
    ) -> WorldFactRecord:
        current = self.get(fact_id)
        fields: dict[str, object] = {
            "statement": self._required_text(statement, "statement")
        }
        if topic_key is not None:
            fields["topic_key"] = self._required_text(topic_key, "topic_key")
        if category is not None:
            fields["category"] = self._required_text(category, "category")
        if title is not None:
            fields["title"] = self._required_text(title, "title")
        if details_json is not None:
            fields["details_json"] = self._json_text(details_json)
        if valid_from is not None or valid_to is not None:
            normalized_from, normalized_to = self._validate_temporal_bounds(
                valid_from if valid_from is not None else current.valid_from,
                valid_to if valid_to is not None else current.valid_to,
            )
            fields.update(valid_from=normalized_from, valid_to=normalized_to)
        if importance is not None:
            if not isinstance(importance, int) or importance < 0:
                raise ValidationError(
                    "importance must be non-negative", field="importance"
                )
            fields["importance"] = importance
        try:
            self._canon_service.update_content(
                "world_fact",
                fact_id,
                fields,
                expected_version=expected_version,
                reason=reason,
            )
        except CanonEntityNotFoundError as exc:
            raise WorldFactNotFoundError("NOT_FOUND") from exc
        return self.get(fact_id)

    def search(self, query: str, limit: int) -> tuple[WorldFactRecord, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0:
            return ()
        return self._repository.search(
            work_id=self._work_id(),
            query=normalized_query,
            limit=min(limit, MAX_SEARCH_LIMIT),
        )

    def list(self, limit: int, offset: int) -> tuple[WorldFactRecord, ...]:
        if limit <= 0 or offset < 0:
            return ()
        return self._repository.list(
            work_id=self._work_id(),
            limit=limit,
            offset=offset,
        )

    def _work_id(self) -> int:
        record = self._work_repository.get()
        if record is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return record.id

    def _validate_temporal_bounds(
        self, valid_from: str | None, valid_to: str | None
    ) -> tuple[str | None, str | None]:
        normalized_from = self._normalize_date(valid_from, field_name="valid_from")
        normalized_to = self._normalize_date(valid_to, field_name="valid_to")
        if normalized_from and normalized_to and normalized_from > normalized_to:
            raise ValueError("valid_to must be on or after valid_from")
        return normalized_from, normalized_to

    def _normalize_date(self, value: str | None, *, field_name: str) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError as exc:
            raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc

    def _json_text(self, value: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(
                "details_json must be JSON text", field="details_json"
            )
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "details_json must be valid JSON", field="details_json"
            ) from exc
        return value

    def _required_text(self, value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return value.strip()
