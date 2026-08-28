from __future__ import annotations

import json
import sqlite3

from novel_core.errors import ValidationError, WorkNotFoundError
from novel_core.repositories.work_repository import WorkRecord, WorkRepository

PRODUCTION_STATUSES = frozenset(
    ("planned", "outlined", "drafting", "revising", "final")
)


class WorkService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = WorkRepository(connection)

    def get(self) -> WorkRecord:
        record = self._repository.get()
        if record is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return record

    def update(
        self,
        working_title: str,
        expected_version: int,
        *,
        genre: str | None = None,
        premise: str | None = None,
        themes_json: str | None = None,
        description: str | None = None,
        production_status: str | None = None,
    ) -> WorkRecord:
        fields: dict[str, object] = {
            "working_title": self._required_text(working_title, "working_title")
        }
        for field_name, value in (
            ("genre", genre),
            ("premise", premise),
            ("description", description),
        ):
            if value is not None:
                fields[field_name] = self._text(value, field_name)
        if themes_json is not None:
            self._validate_json(themes_json)
            fields["themes_json"] = themes_json
        if production_status is not None:
            if production_status not in PRODUCTION_STATUSES:
                raise ValidationError(
                    "unsupported production_status", field="production_status"
                )
            fields["production_status"] = production_status
        self._repository.begin_write()
        try:
            updated = self._repository.update(
                expected_version=expected_version, fields=fields
            )
            self._repository.commit()
            return updated
        except Exception:
            self._repository.rollback()
            raise

    def _required_text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return value.strip()

    def _text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field=field_name)
        return value.strip()

    def _validate_json(self, value: object) -> None:
        if not isinstance(value, str):
            raise ValidationError("themes_json must be valid JSON", field="themes_json")
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "themes_json must be valid JSON", field="themes_json"
            ) from exc
