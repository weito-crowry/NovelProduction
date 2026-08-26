from __future__ import annotations

import json
import sqlite3
from typing import Any

from novel_mcp.errors import (
    CharacterNotFoundError,
    NarrativeNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_mcp.repositories.character_repository import CharacterRepository
from novel_mcp.repositories.character_state_repository import (
    CharacterStateRecord,
    CharacterStateRepository,
)
from novel_mcp.repositories.narrative_repository import NarrativeRepository
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.repositories.world_fact_repository import WorldFactRepository


class CharacterStateService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._repository = CharacterStateRepository(connection)
        self._character_repository = CharacterRepository(connection)
        self._narrative_repository = NarrativeRepository(connection)
        self._world_fact_repository = WorldFactRepository(connection)
        self._work_repository = WorkRepository(connection)

    def set_state(
        self,
        character_id: int,
        episode_id: int,
        *,
        physical_state: str | None = None,
        emotional_state: str | None = None,
        beliefs_json: Any = None,
        location_world_fact_id: int | None = None,
        state_json: Any = None,
        expected_version: int | None = None,
    ) -> CharacterStateRecord:
        work_id = self._work_id()
        self._validate_character(work_id, character_id)
        self._validate_episode(work_id, episode_id)
        if location_world_fact_id is not None:
            self._validate_location(work_id, location_world_fact_id)
        provided = {
            "physical_state": physical_state,
            "emotional_state": emotional_state,
            "beliefs_json": beliefs_json,
            "location_world_fact_id": location_world_fact_id,
            "state_json": state_json,
        }
        self._validate_version_if_present(expected_version)
        self._repository.begin_write()
        try:
            current = self._repository.get(
                work_id=work_id, character_id=character_id, episode_id=episode_id
            )
            if current is None:
                if expected_version is not None:
                    raise ValidationError(
                        "expected_version must be None for a new state",
                        field="expected_version",
                    )
                fields = {
                    "character_id": character_id,
                    "episode_id": episode_id,
                    "physical_state": self._text(
                        physical_state or "", "physical_state"
                    ),
                    "emotional_state": self._text(
                        emotional_state or "", "emotional_state"
                    ),
                    "beliefs_json": self._json_text(
                        {} if beliefs_json is None else beliefs_json, "beliefs_json"
                    ),
                    "location_world_fact_id": location_world_fact_id,
                    "state_json": self._json_text(
                        {} if state_json is None else state_json, "state_json"
                    ),
                }
                state_id = self._repository.create(work_id=work_id, fields=fields)
            else:
                if expected_version is None:
                    raise ValidationError(
                        "expected_version is required for an existing state",
                        field="expected_version",
                    )
                fields = self._update_fields(provided)
                if not fields:
                    raise ValidationError("at least one state field is required")
                if not self._repository.update(
                    work_id=work_id,
                    character_id=character_id,
                    episode_id=episode_id,
                    expected_version=expected_version,
                    fields=fields,
                ):
                    raise VersionConflictError("VERSION_CONFLICT")
                state_id = current.id
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        record = self._repository.get(
            work_id=work_id, character_id=character_id, episode_id=episode_id
        )
        if record is None or record.id != state_id:
            raise sqlite3.IntegrityError("character state retrieval failed")
        return record

    def get_effective_state(
        self, character_id: int, episode_id: int
    ) -> CharacterStateRecord | None:
        work_id = self._work_id()
        self._validate_character(work_id, character_id)
        self._validate_episode(work_id, episode_id)
        return self._repository.effective(
            work_id=work_id, character_id=character_id, episode_id=episode_id
        )

    def history(self, character_id: int) -> tuple[CharacterStateRecord, ...]:
        work_id = self._work_id()
        self._validate_character(work_id, character_id)
        return self._repository.history(work_id=work_id, character_id=character_id)

    def _update_fields(self, values: dict[str, Any]) -> dict[str, object]:
        fields: dict[str, object] = {}
        for field_name in ("physical_state", "emotional_state"):
            value = values[field_name]
            if value is not None:
                fields[field_name] = self._text(value, field_name)
        for field_name in ("beliefs_json", "state_json"):
            value = values[field_name]
            if value is not None:
                fields[field_name] = self._json_text(value, field_name)
        if values["location_world_fact_id"] is not None:
            fields["location_world_fact_id"] = values["location_world_fact_id"]
        return fields

    def _validate_character(self, work_id: int, character_id: int) -> None:
        if self._character_repository.get(work_id=work_id, character_id=character_id):
            return
        if self._character_repository.get_work_id(character_id) is not None:
            raise WorkScopeError()
        raise CharacterNotFoundError("NOT_FOUND")

    def _validate_episode(self, work_id: int, episode_id: int) -> None:
        if self._narrative_repository.get_episode(
            work_id=work_id, episode_id=episode_id
        ):
            return
        if self._narrative_repository.get_episode_work_id(episode_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _validate_location(self, work_id: int, fact_id: int) -> None:
        fact_work_id = self._world_fact_repository.get_work_id(fact_id)
        if fact_work_id is None:
            raise ValidationError(
                "location_world_fact_id was not found", field="location_world_fact_id"
            )
        if fact_work_id != work_id:
            raise WorkScopeError()

    def _validate_version_if_present(self, value: int | None) -> None:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ValidationError(
                "expected_version must be at least 1", field="expected_version"
            )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field=field_name)
        return value.strip()

    def _json_text(self, value: object, field_name: str) -> str:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"{field_name} must be valid JSON", field=field_name
            ) from exc
