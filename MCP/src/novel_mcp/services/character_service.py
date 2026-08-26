from __future__ import annotations

import sqlite3
from uuid import uuid4

from novel_mcp.errors import (
    CanonEntityNotFoundError,
    CharacterNotFoundError,
    ValidationError,
    WorkNotFoundError,
)
from novel_mcp.repositories.character_repository import (
    CharacterRecord,
    CharacterRepository,
)
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.search_service import MAX_SEARCH_LIMIT


class CharacterService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._work_repository = WorkRepository(connection)
        self._repository = CharacterRepository(connection)
        self._canon_service = CanonService(connection)

    def create(self, name: str, profile: str | None) -> CharacterRecord:
        normalized_name = self._required_text(name, "name")
        normalized_profile = "" if profile is None else profile.strip()
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            character_id = self._repository.create(
                work_id=work_id,
                character_key=uuid4().hex,
                name=normalized_name,
                profile=normalized_profile,
            )
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
    ) -> CharacterRecord:
        work_id = self._work_id()
        current = self._repository.get(work_id=work_id, character_id=character_id)
        if current is None:
            raise CharacterNotFoundError("NOT_FOUND")
        normalized_name = (
            self._required_text(name, "name") if name is not None else current.name
        )
        normalized_profile = profile.strip() if profile is not None else current.profile
        try:
            self._canon_service.update_content(
                "character",
                character_id,
                {"display_name": normalized_name, "summary": normalized_profile},
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

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _required_text(self, value: str, field_name: str) -> str:
        try:
            normalized = value.strip()
        except AttributeError as exc:
            raise ValidationError(
                f"{field_name} must be a string", field=field_name
            ) from exc
        if not normalized:
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return normalized
