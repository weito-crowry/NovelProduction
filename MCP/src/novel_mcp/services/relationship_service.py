from __future__ import annotations

import sqlite3

from novel_mcp.errors import (
    CharacterNotFoundError,
    RelationshipNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
)
from novel_mcp.repositories.character_repository import CharacterRepository
from novel_mcp.repositories.relationship_repository import (
    RelationshipRecord,
    RelationshipRepository,
)
from novel_mcp.repositories.work_repository import WorkRepository


class RelationshipService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._work_repository = WorkRepository(connection)
        self._character_repository = CharacterRepository(connection)
        self._repository = RelationshipRepository(connection)

    def create(
        self,
        source_character_id: int,
        target_character_id: int,
        relation_type: str,
    ) -> RelationshipRecord:
        normalized_type = self._required_text(relation_type, "relation_type")
        if source_character_id == target_character_id:
            raise ValidationError("self relationship is not allowed", field="endpoints")
        work_id = self._work_id()
        self._validate_endpoint(work_id, source_character_id)
        self._validate_endpoint(work_id, target_character_id)
        self._repository.begin_write()
        try:
            try:
                relationship_id = self._repository.create(
                    work_id=work_id,
                    source_character_id=source_character_id,
                    target_character_id=target_character_id,
                    relation_type=normalized_type,
                )
            except sqlite3.IntegrityError as exc:
                raise ValidationError("duplicate relationship") from exc
            record = self._repository.get(
                work_id=work_id, relationship_id=relationship_id
            )
            if record is None:
                raise sqlite3.IntegrityError("relationship creation failed")
            self._connection.commit()
            return record
        except Exception:
            self._connection.rollback()
            raise

    def get(self, relationship_id: int) -> RelationshipRecord:
        record = self._repository.get(
            work_id=self._work_id(), relationship_id=relationship_id
        )
        if record is None:
            raise RelationshipNotFoundError("NOT_FOUND")
        return record

    def update(
        self, relationship_id: int, expected_version: int, relation_type: str
    ) -> RelationshipRecord:
        normalized_type = self._required_text(relation_type, "relation_type")
        work_id = self._work_id()
        if (
            self._repository.get(work_id=work_id, relationship_id=relationship_id)
            is None
        ):
            raise RelationshipNotFoundError("NOT_FOUND")
        self._repository.begin_write()
        try:
            if not self._repository.update(
                work_id=work_id,
                relationship_id=relationship_id,
                expected_version=expected_version,
                relation_type=normalized_type,
            ):
                raise VersionConflictError("VERSION_CONFLICT")
            updated = self._repository.get(
                work_id=work_id, relationship_id=relationship_id
            )
            if updated is None:
                raise RelationshipNotFoundError("NOT_FOUND")
            self._connection.commit()
            return updated
        except Exception:
            self._connection.rollback()
            raise

    def search(
        self, character_id: int | None, limit: int
    ) -> tuple[RelationshipRecord, ...]:
        if limit <= 0:
            return ()
        work_id = self._work_id()
        if character_id is not None:
            self._validate_endpoint(work_id, character_id)
        return self._repository.search(
            work_id=work_id, character_id=character_id, limit=limit
        )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _validate_endpoint(self, work_id: int, character_id: int) -> None:
        if (
            self._character_repository.get(work_id=work_id, character_id=character_id)
            is None
        ):
            raise CharacterNotFoundError("NOT_FOUND")

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
