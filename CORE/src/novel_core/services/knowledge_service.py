from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from novel_core.errors import (
    CharacterNotFoundError,
    NarrativeNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_core.repositories.character_repository import CharacterRepository
from novel_core.repositories.information_repository import (
    InformationItemRecord,
    InformationRepository,
)
from novel_core.repositories.knowledge_repository import (
    CharacterKnowledgeEventRecord,
    KnowledgeRepository,
)
from novel_core.repositories.narrative_repository import NarrativeRepository
from novel_core.repositories.work_repository import WorkRepository

KNOWLEDGE_STATES = frozenset(
    ("suspects", "believes", "knows", "confirmed", "doubts", "rejected")
)
KNOWN_STATES = frozenset(("suspects", "believes", "knows", "confirmed"))


@dataclass(frozen=True, slots=True)
class EffectiveKnowledgeRecord:
    knowledge_state: str
    event_episode_id: int
    event_id: int
    event_version: int
    information_item: InformationItemRecord


class KnowledgeService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = KnowledgeRepository(connection)
        self._character_repository = CharacterRepository(connection)
        self._information_repository = InformationRepository(connection)
        self._narrative_repository = NarrativeRepository(connection)
        self._work_repository = WorkRepository(connection)

    def set_character_knowledge(
        self,
        character_id: int,
        information_item_id: int,
        episode_id: int,
        knowledge_state: str,
        note: str = "",
        *,
        expected_version: int | None = None,
    ) -> CharacterKnowledgeEventRecord:
        work_id = self._work_id()
        self._validate_character(work_id, character_id)
        self._validate_information(work_id, information_item_id)
        self._validate_episode(work_id, episode_id)
        self._validate_state(knowledge_state)
        normalized_note = self._text(note, "note")
        self._validate_optional_version(expected_version)
        self._repository.begin_write()
        try:
            current = self._repository.get(
                work_id=work_id,
                character_id=character_id,
                information_item_id=information_item_id,
                episode_id=episode_id,
            )
            if current is None:
                if expected_version is not None:
                    raise ValidationError(
                        "expected_version must be None for a new knowledge event",
                        field="expected_version",
                    )
                event_id = self._repository.create(
                    work_id=work_id,
                    fields={
                        "character_id": character_id,
                        "information_item_id": information_item_id,
                        "episode_id": episode_id,
                        "knowledge_state": knowledge_state,
                        "note": normalized_note,
                    },
                )
            else:
                if expected_version is None:
                    raise ValidationError(
                        "expected_version is required for an existing knowledge event",
                        field="expected_version",
                    )
                if not self._repository.update(
                    work_id=work_id,
                    character_id=character_id,
                    information_item_id=information_item_id,
                    episode_id=episode_id,
                    expected_version=expected_version,
                    fields={
                        "knowledge_state": knowledge_state,
                        "note": normalized_note,
                    },
                ):
                    raise VersionConflictError("VERSION_CONFLICT")
                event_id = current.id
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        result = self._repository.get(
            work_id=work_id,
            character_id=character_id,
            information_item_id=information_item_id,
            episode_id=episode_id,
        )
        if result is None or result.id != event_id:
            raise sqlite3.IntegrityError("knowledge event retrieval failed")
        return result

    def get_character_knowledge(
        self, character_id: int, episode_id: int
    ) -> tuple[EffectiveKnowledgeRecord, ...]:
        work_id = self._work_id()
        self._validate_character(work_id, character_id)
        target_order = self._episode_order(work_id, episode_id)
        effective: dict[
            int, tuple[tuple[int, int, int], CharacterKnowledgeEventRecord]
        ] = {}
        for event in self._repository.list_for_character(
            work_id=work_id, character_id=character_id
        ):
            event_order = self._episode_order(work_id, event.episode_id)
            if event_order > target_order:
                continue
            rank = (*event_order, event.id)
            current = effective.get(event.information_item_id)
            if current is None or rank > current[0]:
                effective[event.information_item_id] = (rank, event)

        results: list[EffectiveKnowledgeRecord] = []
        for _, event in sorted(effective.values(), key=lambda value: value[0]):
            information_item = self._information_repository.get(
                work_id=work_id, item_id=event.information_item_id
            )
            if information_item is None or (
                information_item.canon_status == "deprecated"
            ):
                continue
            results.append(
                EffectiveKnowledgeRecord(
                    knowledge_state=event.knowledge_state,
                    event_episode_id=event.episode_id,
                    event_id=event.id,
                    event_version=event.version,
                    information_item=information_item,
                )
            )
        return tuple(results)

    def get_character_knowledge_event(
        self, character_id: int, information_item_id: int, episode_id: int
    ) -> CharacterKnowledgeEventRecord | None:
        work_id = self._work_id()
        self._validate_character(work_id, character_id)
        self._validate_information(work_id, information_item_id)
        self._validate_episode(work_id, episode_id)
        return self._repository.get(
            work_id=work_id,
            character_id=character_id,
            information_item_id=information_item_id,
            episode_id=episode_id,
        )

    def get_known_information(
        self, character_id: int, episode_id: int
    ) -> tuple[InformationItemRecord, ...]:
        return tuple(
            result.information_item
            for result in self.get_character_knowledge(character_id, episode_id)
            if result.knowledge_state in KNOWN_STATES
        )

    def _validate_character(self, work_id: int, character_id: int) -> None:
        if self._character_repository.get(work_id=work_id, character_id=character_id):
            return
        if self._character_repository.get_work_id(character_id) is not None:
            raise WorkScopeError()
        raise CharacterNotFoundError("NOT_FOUND")

    def _validate_information(self, work_id: int, information_item_id: int) -> None:
        if self._information_repository.get(
            work_id=work_id, item_id=information_item_id
        ):
            return
        if self._information_repository.get_work_id(information_item_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _validate_episode(self, work_id: int, episode_id: int) -> None:
        if self._narrative_repository.get_episode(
            work_id=work_id, episode_id=episode_id
        ):
            return
        if self._narrative_repository.get_episode_work_id(episode_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _episode_order(self, work_id: int, episode_id: int) -> tuple[int, int]:
        self._validate_episode(work_id, episode_id)
        order = self._narrative_repository.get_episode_narrative_order(
            work_id=work_id, episode_id=episode_id
        )
        if order is None:
            raise NarrativeNotFoundError()
        return order

    def _validate_state(self, value: object) -> None:
        if not isinstance(value, str) or value not in KNOWLEDGE_STATES:
            raise ValidationError(
                "unsupported knowledge_state", field="knowledge_state"
            )

    def _validate_optional_version(self, value: int | None) -> None:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ValidationError(
                "expected_version must be at least 1", field="expected_version"
            )

    def _text(self, value: object, field: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field} must be a string", field=field)
        return value.strip()

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id
