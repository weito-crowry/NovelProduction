from __future__ import annotations

import sqlite3

from novel_mcp.errors import (
    DeprecatedCanonForbiddenError,
    NarrativeNotFoundError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_mcp.models.outline import (
    EpisodeOutline,
    OutlineParticipant,
    OutlineReferences,
    ProtectedInformationGuard,
    RevealBoundary,
    SafeCharacterProfile,
    SafeInformationItem,
    SafeTimelineEvent,
    SafeWorldFact,
)
from novel_mcp.repositories.character_repository import CharacterRecord
from novel_mcp.repositories.disclosure_repository import ReaderDisclosureRecord
from novel_mcp.repositories.episode_reference_repository import EpisodeReferenceRecord
from novel_mcp.repositories.information_repository import InformationItemRecord
from novel_mcp.repositories.narrative_repository import EpisodeRecord
from novel_mcp.repositories.outline_repository import OutlineRepository
from novel_mcp.repositories.work_repository import WorkRepository

GENERIC_GUARD = (
    "This episode references protected information that has not yet been "
    "disclosed. Do not reveal its protected content."
)


class OutlineService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = OutlineRepository(connection)
        self._work_repository = WorkRepository(connection)

    def get_episode_outline(self, episode_id: int) -> EpisodeOutline:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        episode = self._get_episode(work.id, episode_id)
        if episode.canon_status == "deprecated":
            raise DeprecatedCanonForbiddenError()
        target_order = self._episode_order(work.id, episode_id)
        scenes = tuple(
            scene
            for scene in self._repository.list_scenes(work.id, episode_id)
            if scene.canon_status != "deprecated"
        )
        references = self._repository.list_references(work.id, episode_id)
        participants = self._participants(work.id, references)
        world_facts = self._world_facts(work.id, references)
        timeline_events = self._timeline_events(work.id, references)
        information, guards = self._information(work.id, target_order, references)
        return EpisodeOutline(
            episode=episode,
            scenes=scenes,
            participants=participants,
            references=OutlineReferences(
                world_facts=world_facts,
                timeline_events=timeline_events,
                information=information,
            ),
            protected_information_guards=guards,
        )

    def _get_episode(self, work_id: int, episode_id: int) -> EpisodeRecord:
        episode = self._repository.get_episode(work_id, episode_id)
        if episode is not None:
            return episode
        if self._repository.get_episode_work_id(episode_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _episode_order(self, work_id: int, episode_id: int) -> tuple[int, int]:
        order = self._repository.get_episode_order(work_id, episode_id)
        if order is None:
            raise NarrativeNotFoundError()
        return order

    def _participants(
        self, work_id: int, references: tuple[EpisodeReferenceRecord, ...]
    ) -> tuple[OutlineParticipant, ...]:
        result: list[OutlineParticipant] = []
        for reference in references:
            if reference.reference_type != "character":
                continue
            character = self._repository.get_character(work_id, reference.target_id)
            if character is None or character.canon_status == "deprecated":
                continue
            result.append(
                OutlineParticipant(
                    profile=_safe_character(character),
                    role=reference.role or "participant",
                )
            )
        return tuple(result)

    def _world_facts(
        self, work_id: int, references: tuple[EpisodeReferenceRecord, ...]
    ) -> tuple[SafeWorldFact, ...]:
        result: list[SafeWorldFact] = []
        for reference in references:
            if reference.reference_type != "world_fact":
                continue
            fact = self._repository.get_world_fact(work_id, reference.target_id)
            if fact is None or fact.canon_status == "deprecated":
                continue
            result.append(
                SafeWorldFact(
                    id=fact.id,
                    topic_key=fact.topic_key,
                    category=fact.category,
                    title=fact.title,
                    statement=fact.statement,
                    valid_from=fact.valid_from,
                    valid_to=fact.valid_to,
                    canon_status=fact.canon_status,
                    importance=fact.importance,
                )
            )
        return tuple(result)

    def _timeline_events(
        self, work_id: int, references: tuple[EpisodeReferenceRecord, ...]
    ) -> tuple[SafeTimelineEvent, ...]:
        result: list[SafeTimelineEvent] = []
        for reference in references:
            if reference.reference_type != "timeline_event":
                continue
            event = self._repository.get_timeline_event(work_id, reference.target_id)
            if event is None or event.canon_status == "deprecated":
                continue
            result.append(
                SafeTimelineEvent(
                    id=event.id,
                    event_key=event.event_key,
                    time_start=event.time_start,
                    time_end=event.time_end,
                    date_precision=event.date_precision,
                    date_display=event.date_display,
                    title=event.title,
                    description=event.description,
                    category=event.category,
                    location_world_fact_id=event.location_world_fact_id,
                    cause_summary=event.cause_summary,
                    consequence_summary=event.consequence_summary,
                    canon_status=event.canon_status,
                    importance=event.importance,
                )
            )
        return tuple(result)

    def _information(
        self,
        work_id: int,
        target_order: tuple[int, int],
        references: tuple[EpisodeReferenceRecord, ...],
    ) -> tuple[tuple[SafeInformationItem, ...], tuple[ProtectedInformationGuard, ...]]:
        items: list[SafeInformationItem] = []
        guards: list[ProtectedInformationGuard] = []
        for reference in references:
            if reference.reference_type != "information":
                continue
            item = self._repository.get_information(work_id, reference.target_id)
            if item is None or item.canon_status == "deprecated":
                continue
            disclosure = self._repository.get_disclosure(work_id, item.id)
            boundary = self._boundary(work_id, disclosure)
            if boundary is not None and boundary <= target_order:
                items.append(_safe_information(item))
            else:
                guards.append(
                    ProtectedInformationGuard(
                        information_item_id=item.id,
                        reason=(
                            "reader_disclosure_after_target"
                            if boundary is not None
                            else "reader_disclosure_missing"
                        ),
                        guard_text=_safe_guard(item),
                        reveal_boundary=(
                            None
                            if disclosure is None or boundary is None
                            else RevealBoundary(
                                episode_id=disclosure.episode_id,
                                chapter_position=boundary[0],
                                episode_position=boundary[1],
                            )
                        ),
                    )
                )
        return tuple(items), tuple(guards)

    def _boundary(
        self, work_id: int, disclosure: ReaderDisclosureRecord | None
    ) -> tuple[int, int] | None:
        if disclosure is None:
            return None
        order = self._repository.get_episode_order(work_id, disclosure.episode_id)
        if order is None:
            return None
        return order


def _safe_character(character: CharacterRecord) -> SafeCharacterProfile:
    return SafeCharacterProfile(
        id=character.id,
        character_key=character.character_key,
        display_name=character.display_name,
        entity_type=character.entity_type,
        description=character.description,
        birth_date=character.birth_date,
        physical_description=character.physical_description,
        occupation=character.occupation,
        core_beliefs=character.core_beliefs,
        goals=character.goals,
        fears=character.fears,
        personality=character.personality,
        speech_style=character.speech_style,
        ai_attitude=character.ai_attitude,
        genetic_modification_attitude=character.genetic_modification_attitude,
        canon_status=character.canon_status,
    )


def _safe_information(item: InformationItemRecord) -> SafeInformationItem:
    return SafeInformationItem(
        id=item.id,
        statement=item.statement,
        truth_status=item.truth_status,
        canon_status=item.canon_status,
        importance=item.importance,
    )


def _safe_guard(item: InformationItemRecord) -> str:
    if item.authoring_guard and item.statement not in item.authoring_guard:
        return item.authoring_guard
    return GENERIC_GUARD
