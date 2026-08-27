from __future__ import annotations

import json
import sqlite3
from datetime import date
from uuid import uuid4

from novel_core.errors import (
    CanonEntityNotFoundError,
    CharacterNotFoundError,
    ValidationError,
    WorkNotFoundError,
)
from novel_core.repositories.character_repository import (
    CharacterRecord,
    CharacterRepository,
)
from novel_core.repositories.work_repository import WorkRepository
from novel_core.services.canon_service import CanonService
from novel_core.services.search_service import MAX_SEARCH_LIMIT

_ENTITY_TYPES = frozenset(("human", "ai", "organization"))
_TEXT_FIELDS = (
    "physical_description",
    "occupation",
    "core_beliefs",
    "goals",
    "fears",
    "personality",
    "speech_style",
    "ai_attitude",
    "genetic_modification_attitude",
    "private_notes",
)


class CharacterService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._work_repository = WorkRepository(connection)
        self._repository = CharacterRepository(connection)
        self._canon_service = CanonService(connection)

    def create(
        self,
        name: str | None = None,
        profile: str | None = None,
        *,
        character_key: str | None = None,
        display_name: str | None = None,
        entity_type: str = "human",
        description: str | None = None,
        birth_date: str | None = None,
        death_date: str | None = None,
        physical_description: str = "",
        occupation: str = "",
        core_beliefs: str = "",
        goals: str = "",
        fears: str = "",
        personality: str = "",
        speech_style: str = "",
        ai_attitude: str = "",
        genetic_modification_attitude: str = "",
        private_notes: str = "",
        profile_json: str = "{}",
    ) -> CharacterRecord:
        normalized_name = self._required_text(
            display_name if display_name is not None else name, "display_name"
        )
        normalized_description = (
            description if description is not None else (profile or "")
        ).strip()
        fields = self._normalize_fields(
            character_key=character_key or uuid4().hex,
            display_name=normalized_name,
            entity_type=entity_type,
            description=normalized_description,
            birth_date=birth_date,
            death_date=death_date,
            physical_description=physical_description,
            occupation=occupation,
            core_beliefs=core_beliefs,
            goals=goals,
            fears=fears,
            personality=personality,
            speech_style=speech_style,
            ai_attitude=ai_attitude,
            genetic_modification_attitude=genetic_modification_attitude,
            private_notes=private_notes,
            profile_json=profile_json,
        )
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            character_id = self._repository.create(work_id=work_id, fields=fields)
            record = self._repository.get(work_id=work_id, character_id=character_id)
            if record is None:
                raise sqlite3.IntegrityError("character creation failed")
            self._repository.commit()
            return record
        except Exception:
            self._repository.rollback()
            raise

    def get(self, character_id: int) -> CharacterRecord:
        record = self._repository.get(
            work_id=self._work_id(), character_id=character_id
        )
        if record is None:
            raise CharacterNotFoundError("NOT_FOUND")
        return record

    def update(
        self,
        character_id: int,
        expected_version: int,
        *,
        name: str | None = None,
        profile: str | None = None,
        reason: str | None = None,
        character_key: str | None = None,
        display_name: str | None = None,
        entity_type: str | None = None,
        description: str | None = None,
        birth_date: str | None = None,
        death_date: str | None = None,
        physical_description: str | None = None,
        occupation: str | None = None,
        core_beliefs: str | None = None,
        goals: str | None = None,
        fears: str | None = None,
        personality: str | None = None,
        speech_style: str | None = None,
        ai_attitude: str | None = None,
        genetic_modification_attitude: str | None = None,
        private_notes: str | None = None,
        profile_json: str | None = None,
    ) -> CharacterRecord:
        current = self.get(character_id)
        fields: dict[str, object] = {}
        selected_name = display_name if display_name is not None else name
        selected_description = description if description is not None else profile
        if selected_name is not None:
            fields["display_name"] = self._required_text(selected_name, "display_name")
        if selected_description is not None:
            fields["description"] = selected_description.strip()
        for key, value in (
            ("character_key", character_key),
            ("entity_type", entity_type),
            ("birth_date", birth_date),
            ("death_date", death_date),
            ("physical_description", physical_description),
            ("occupation", occupation),
            ("core_beliefs", core_beliefs),
            ("goals", goals),
            ("fears", fears),
            ("personality", personality),
            ("speech_style", speech_style),
            ("ai_attitude", ai_attitude),
            ("genetic_modification_attitude", genetic_modification_attitude),
            ("private_notes", private_notes),
        ):
            if value is not None:
                fields[key] = self._required_or_empty(value, key)
        if entity_type is not None and entity_type not in _ENTITY_TYPES:
            raise ValidationError("unsupported entity_type", field="entity_type")
        if birth_date is not None:
            fields["birth_date"] = self._normalize_date(birth_date, "birth_date")
        if death_date is not None:
            fields["death_date"] = self._normalize_date(death_date, "death_date")
        if profile_json is not None:
            self._validate_json(profile_json, "profile_json")
            fields["profile_json"] = profile_json
        if not fields:
            fields["description"] = current.description
        try:
            self._canon_service.update_content(
                "character",
                character_id,
                fields,
                expected_version=expected_version,
                reason=reason,
            )
        except CanonEntityNotFoundError as exc:
            raise CharacterNotFoundError("NOT_FOUND") from exc
        return self.get(character_id)

    def search(self, query: str, limit: int) -> tuple[CharacterRecord, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0:
            return ()
        return self._repository.search(
            work_id=self._work_id(),
            query=normalized_query,
            limit=min(limit, MAX_SEARCH_LIMIT),
        )

    def _normalize_fields(self, **fields: object) -> dict[str, object]:
        entity_type = fields["entity_type"]
        if entity_type not in _ENTITY_TYPES:
            raise ValidationError("unsupported entity_type", field="entity_type")
        for field in _TEXT_FIELDS:
            fields[field] = self._required_or_empty(fields[field], field)
        for field in ("birth_date", "death_date"):
            if fields[field] is not None:
                fields[field] = self._normalize_date(fields[field], field)
        self._validate_json(fields["profile_json"], "profile_json")
        return fields

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _required_text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return value.strip()

    def _required_or_empty(self, value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field=field_name)
        return value.strip()

    def _normalize_date(self, value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be YYYY-MM-DD", field=field_name)
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError as exc:
            raise ValidationError(
                f"{field_name} must be YYYY-MM-DD", field=field_name
            ) from exc

    def _validate_json(self, value: object, field_name: str) -> None:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be valid JSON", field=field_name)
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"{field_name} must be valid JSON", field=field_name
            ) from exc
