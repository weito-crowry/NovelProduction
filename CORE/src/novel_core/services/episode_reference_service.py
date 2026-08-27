from __future__ import annotations

import sqlite3
from typing import Protocol

from novel_core.errors import (
    CharacterNotFoundError,
    NarrativeNotFoundError,
    RelationshipIntegrityError,
    TimelineEventNotFoundError,
    ValidationError,
    WorkNotFoundError,
    WorkScopeError,
    WorldFactNotFoundError,
)
from novel_core.repositories.character_repository import CharacterRepository
from novel_core.repositories.episode_reference_repository import (
    EpisodeReferenceRecord,
    EpisodeReferenceRepository,
)
from novel_core.repositories.information_repository import InformationRepository
from novel_core.repositories.narrative_repository import NarrativeRepository
from novel_core.repositories.timeline_repository import TimelineRepository
from novel_core.repositories.work_repository import WorkRepository
from novel_core.repositories.world_fact_repository import WorldFactRepository

REFERENCE_TYPES = frozenset(
    ("character", "world_fact", "timeline_event", "information")
)


class _WorkIdRepository(Protocol):
    def get_work_id(self, entity_id: int) -> int | None: ...


class EpisodeReferenceService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = EpisodeReferenceRepository(connection)
        self._narrative_repository = NarrativeRepository(connection)
        self._character_repository = CharacterRepository(connection)
        self._world_fact_repository = WorldFactRepository(connection)
        self._timeline_repository = TimelineRepository(connection)
        self._information_repository = InformationRepository(connection)
        self._work_repository = WorkRepository(connection)

    def add(
        self,
        episode_id: int,
        reference_type: str,
        target_id: int,
        *,
        role: str = "participant",
    ) -> EpisodeReferenceRecord:
        self._validate_type(reference_type)
        work_id = self._work_id()
        self._validate_episode(work_id, episode_id)
        self._validate_target(work_id, reference_type, target_id)
        normalized_role = (
            self._normalize_role(role) if reference_type == "character" else None
        )
        if reference_type != "character" and role != "participant":
            raise ValidationError(
                "role is only supported for character references", field="role"
            )
        self._repository.begin_write()
        try:
            try:
                reference_id = self._repository.add(
                    work_id=work_id,
                    episode_id=episode_id,
                    reference_type=reference_type,
                    target_id=target_id,
                    role=normalized_role,
                )
            except sqlite3.IntegrityError as exc:
                raise RelationshipIntegrityError("duplicate episode reference") from exc
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        for reference in self._repository.list(
            work_id=work_id, episode_id=episode_id, reference_type=reference_type
        ):
            if reference.id == reference_id:
                return reference
        raise sqlite3.IntegrityError("episode reference retrieval failed")

    def remove(self, episode_id: int, reference_type: str, target_id: int) -> bool:
        self._validate_type(reference_type)
        work_id = self._work_id()
        self._validate_episode(work_id, episode_id)
        self._repository.begin_write()
        try:
            removed = self._repository.remove(
                work_id=work_id,
                episode_id=episode_id,
                reference_type=reference_type,
                target_id=target_id,
            )
            self._repository.commit()
            return removed
        except Exception:
            self._repository.rollback()
            raise

    def list(
        self, episode_id: int, *, reference_type: str | None = None
    ) -> tuple[EpisodeReferenceRecord, ...]:
        if reference_type is not None:
            self._validate_type(reference_type)
        work_id = self._work_id()
        self._validate_episode(work_id, episode_id)
        return self._repository.list(
            work_id=work_id, episode_id=episode_id, reference_type=reference_type
        )

    add_reference = add
    remove_reference = remove
    list_references = list

    def _validate_type(self, reference_type: object) -> None:
        if not isinstance(reference_type, str) or reference_type not in REFERENCE_TYPES:
            raise ValidationError("unsupported reference_type", field="reference_type")

    def _validate_episode(self, work_id: int, episode_id: int) -> None:
        if self._narrative_repository.get_episode(
            work_id=work_id, episode_id=episode_id
        ):
            return
        if self._narrative_repository.get_episode_work_id(episode_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _validate_target(
        self, work_id: int, reference_type: str, target_id: int
    ) -> None:
        repositories: dict[str, _WorkIdRepository] = {
            "character": self._character_repository,
            "world_fact": self._world_fact_repository,
            "timeline_event": self._timeline_repository,
            "information": self._information_repository,
        }
        repository = repositories[reference_type]
        target_work_id = repository.get_work_id(target_id)
        if target_work_id is None:
            errors = {
                "character": CharacterNotFoundError,
                "world_fact": WorldFactNotFoundError,
                "timeline_event": TimelineEventNotFoundError,
                "information": NarrativeNotFoundError,
            }
            raise errors[reference_type]("NOT_FOUND")
        if target_work_id != work_id:
            raise WorkScopeError()

    def _normalize_role(self, role: object) -> str:
        if not isinstance(role, str):
            raise ValidationError("role must be a string", field="role")
        normalized = role.strip()
        if not 1 <= len(normalized) <= 120:
            raise ValidationError("role must contain 1 to 120 characters", field="role")
        return normalized

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id
