from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from novel_core.errors import (
    CanonEntityNotFoundError,
    NarrativeNotFoundError,
    ValidationError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_core.repositories.information_repository import (
    InformationItemRecord,
    InformationRepository,
)
from novel_core.repositories.work_repository import WorkRepository
from novel_core.services.canon_service import CanonService

TRUTH_STATUSES = frozenset(("true", "false", "uncertain", "subjective"))
CANON_STATUSES = frozenset(("idea", "draft", "canon", "deprecated"))
MAX_INFORMATION_SEARCH_LIMIT = 100


class InformationService:
    def __init__(
        self, connection: sqlite3.Connection, *, force_fallback: bool = False
    ) -> None:
        self._connection = connection
        self._repository = InformationRepository(
            connection, force_fallback=force_fallback
        )
        self._work_repository = WorkRepository(connection)
        self._canon_service = CanonService(connection)

    @property
    def last_search_strategy(self) -> str:
        return self._repository.last_strategy

    def create_information(
        self,
        statement: str,
        *,
        truth_status: str = "uncertain",
        authoring_guard: str = "",
        notes_json: Any = None,
        canon_status: str = "draft",
        importance: int = 0,
    ) -> InformationItemRecord:
        fields = self._fields(
            statement=statement,
            truth_status=truth_status,
            authoring_guard=authoring_guard,
            notes_json={} if notes_json is None else notes_json,
            canon_status=canon_status,
            importance=importance,
        )
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            item_id = self._repository.create(work_id=work_id, fields=fields)
            record = self._repository.get(work_id=work_id, item_id=item_id)
            if record is None:
                raise sqlite3.IntegrityError("information creation failed")
            self._repository.commit()
            return record
        except Exception:
            self._repository.rollback()
            raise

    def get_information(self, item_id: int) -> InformationItemRecord:
        work_id = self._work_id()
        record = self._repository.get(work_id=work_id, item_id=item_id)
        if record is None:
            other_work = self._repository.get_work_id(item_id)
            if other_work is not None and other_work != work_id:
                raise WorkScopeError()
            raise NarrativeNotFoundError()
        return record

    def update_information(
        self,
        item_id: int,
        expected_version: int,
        *,
        statement: str | None = None,
        truth_status: str | None = None,
        authoring_guard: str | None = None,
        notes_json: Any = None,
        importance: int | None = None,
        canon_status: str | None = None,
        reason: str | None = None,
    ) -> InformationItemRecord:
        self._validate_version(expected_version)
        self.get_information(item_id)
        fields: dict[str, object] = {}
        if statement is not None:
            fields["statement"] = self._required_text(statement, "statement")
        if truth_status is not None:
            self._validate_choice(truth_status, TRUTH_STATUSES, "truth_status")
            fields["truth_status"] = truth_status
        if authoring_guard is not None:
            fields["authoring_guard"] = self._text(authoring_guard, "authoring_guard")
        if notes_json is not None:
            fields["notes_json"] = self._json_text(notes_json, "notes_json")
        if importance is not None:
            self._validate_importance(importance)
            fields["importance"] = importance
        if canon_status is not None:
            self._validate_choice(canon_status, CANON_STATUSES, "canon_status")
            fields["canon_status"] = canon_status
        if not fields:
            raise ValidationError("at least one information field is required")
        try:
            normalized = dict(fields)
            target_status = cast(str | None, normalized.pop("canon_status", None))
            self._canon_service.update_content(
                "information_item",
                item_id,
                normalized,
                expected_version=expected_version,
                reason=reason,
                target_status=target_status,
            )
        except CanonEntityNotFoundError as exc:
            raise NarrativeNotFoundError() from exc
        return self.get_information(item_id)

    def search_information(
        self, query: str, limit: int
    ) -> tuple[InformationItemRecord, ...]:
        if not isinstance(query, str):
            raise ValidationError("query must be a string", field="query")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 0 <= limit <= MAX_INFORMATION_SEARCH_LIMIT
        ):
            raise ValidationError("limit must be between 0 and 100", field="limit")
        normalized = query.strip()
        if not normalized or limit == 0:
            return ()
        return self._repository.search(
            work_id=self._work_id(), query=normalized, limit=limit
        )

    def list(self, limit: int, offset: int) -> tuple[InformationItemRecord, ...]:
        if limit <= 0 or offset < 0:
            return ()
        return self._repository.list(
            work_id=self._work_id(), limit=limit, offset=offset
        )

    def _fields(self, **values: Any) -> dict[str, object]:
        fields = {
            "statement": self._required_text(values["statement"], "statement"),
            "truth_status": values["truth_status"],
            "authoring_guard": self._text(values["authoring_guard"], "authoring_guard"),
            "notes_json": self._json_text(values["notes_json"], "notes_json"),
            "canon_status": values["canon_status"],
            "importance": values["importance"],
        }
        self._validate_choice(fields["truth_status"], TRUTH_STATUSES, "truth_status")
        self._validate_choice(fields["canon_status"], CANON_STATUSES, "canon_status")
        self._validate_importance(fields["importance"])
        return fields

    def _validate_choice(
        self, value: object, choices: frozenset[str], field: str
    ) -> None:
        if not isinstance(value, str) or value not in choices:
            raise ValidationError(f"unsupported {field}", field=field)

    def _validate_importance(self, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError("importance must be non-negative", field="importance")

    def _validate_version(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError(
                "expected_version must be at least 1", field="expected_version"
            )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _required_text(self, value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field} must be non-empty", field=field)
        return value.strip()

    def _text(self, value: object, field: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field} must be a string", field=field)
        return value.strip()

    def _json_text(self, value: object, field: str) -> str:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field} must be valid JSON", field=field) from exc
