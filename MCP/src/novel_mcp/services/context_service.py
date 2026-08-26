from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from novel_mcp.errors import NarrativeNotFoundError, ValidationError, WorkNotFoundError
from novel_mcp.models.context import (
    ContextParticipant,
    EffectiveCharacterState,
    EffectiveRelationship,
    EpisodeContext,
    ParticipantKnownInformation,
    PreviousEpisodeSummary,
    ReaderContext,
    RecentContext,
)
from novel_mcp.models.outline import (
    EpisodeOutline,
    ProtectedInformationGuard,
    RevealBoundary,
    SafeInformationItem,
)
from novel_mcp.repositories.context_repository import ContextRepository
from novel_mcp.repositories.disclosure_repository import ReaderDisclosureRecord
from novel_mcp.repositories.information_repository import InformationItemRecord
from novel_mcp.repositories.knowledge_repository import CharacterKnowledgeEventRecord
from novel_mcp.repositories.narrative_repository import EpisodeRecord
from novel_mcp.repositories.outline_repository import OutlineRepository
from novel_mcp.repositories.relationship_repository import RelationshipRecord
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.knowledge_service import KNOWN_STATES
from novel_mcp.services.outline_service import GENERIC_GUARD, OutlineService
from novel_mcp.services.relationship_service import RelationshipService

PREVIOUS_SUMMARIES_MAX = 2
PREVIOUS_DRAFT_TAIL_CHARS = 4000
WORLD_FACTS_MAX = 30
TIMELINE_EVENTS_MAX = 30
INFORMATION_ITEMS_MAX = 50


@dataclass(frozen=True, slots=True)
class _InformationCandidate:
    item: SafeInformationItem
    direct_reference: bool
    disclosure_order: tuple[int, int]


class ContextService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = ContextRepository(connection)
        self._work_repository = WorkRepository(connection)
        self._outline_service = OutlineService(connection)
        self._outline_repository = OutlineRepository(connection)
        self._relationship_service = RelationshipService(connection)

    def build_episode_context(self, episode_id: int) -> EpisodeContext:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        outline = self._outline_service.get_episode_outline(episode_id)
        target_order = self._episode_order(work.id, episode_id)
        foreshadowing_notes = _parse_foreshadowing(
            outline.episode.foreshadowing_notes_json
        )

        participants, participant_candidates, participant_guards = self._participants(
            work.id, episode_id, target_order, outline
        )
        reader_context, information_omitted = self._reader_context(
            work.id, target_order, outline, participant_candidates
        )
        participants = self._limit_participant_information(participants, reader_context)
        guards = self._merge_guards(
            outline.protected_information_guards, participant_guards
        )
        world_facts = tuple(
            sorted(
                outline.references.world_facts,
                key=lambda item: (-item.importance, item.id),
            )[:WORLD_FACTS_MAX]
        )
        timeline_events = tuple(
            sorted(
                outline.references.timeline_events,
                key=lambda item: (-item.importance, item.time_start or "", item.id),
            )[:TIMELINE_EVENTS_MAX]
        )
        recent_context, previous_omitted, draft_truncated = self._recent_context(
            work.id, target_order
        )
        context_meta = self._context_meta(
            target_order=target_order,
            world_facts_returned=len(world_facts),
            world_facts_total=len(outline.references.world_facts),
            timeline_events_returned=len(timeline_events),
            timeline_events_total=len(outline.references.timeline_events),
            information_returned=(
                len(reader_context.known_before_episode)
                + len(reader_context.reveal_this_episode)
            ),
            information_total=information_omitted
            + len(reader_context.known_before_episode),
            previous_returned=len(recent_context.previous_episode_summaries),
            previous_total=previous_omitted
            + len(recent_context.previous_episode_summaries),
            previous_draft_tail=len(recent_context.previous_draft_tail),
            draft_truncated=draft_truncated,
            guard_count=len(guards),
        )
        return EpisodeContext(
            episode=outline.episode,
            scenes=outline.scenes,
            participants=participants,
            world_facts=world_facts,
            timeline_events=timeline_events,
            reader_context=reader_context,
            protected_information_guards=guards,
            recent_context=recent_context,
            foreshadowing_notes=foreshadowing_notes,
            context_meta=context_meta,
        )

    def _episode_order(self, work_id: int, episode_id: int) -> tuple[int, int]:
        order = self._repository.get_episode_order(work_id, episode_id)
        if order is None:
            raise NarrativeNotFoundError()
        return order

    def _participants(
        self,
        work_id: int,
        episode_id: int,
        target_order: tuple[int, int],
        outline: EpisodeOutline,
    ) -> tuple[
        tuple[ContextParticipant, ...],
        tuple[_InformationCandidate, ...],
        tuple[ProtectedInformationGuard, ...],
    ]:
        participants: list[ContextParticipant] = []
        candidates: list[_InformationCandidate] = []
        guards: list[ProtectedInformationGuard] = []
        for participant in outline.participants:
            character_id = participant.profile.id
            state = self._repository.effective_state(work_id, character_id, episode_id)
            relationships = tuple(
                _safe_relationship(record, character_id)
                for record in self._relationship_service.effective_at(
                    episode_id, character_id
                )
            )
            known, known_candidates, known_guards = self._known_information(
                work_id, character_id, target_order
            )
            participants.append(
                ContextParticipant(
                    profile=participant.profile,
                    effective_state=(
                        None
                        if state is None
                        else EffectiveCharacterState(
                            state_id=state.id,
                            source_episode_id=state.episode_id,
                            physical_state=state.physical_state,
                            emotional_state=state.emotional_state,
                            location_world_fact_id=state.location_world_fact_id,
                        )
                    ),
                    effective_relationships=relationships,
                    known_information=known,
                )
            )
            candidates.extend(known_candidates)
            guards.extend(known_guards)
        return tuple(participants), tuple(candidates), tuple(guards)

    def _known_information(
        self, work_id: int, character_id: int, target_order: tuple[int, int]
    ) -> tuple[
        tuple[ParticipantKnownInformation, ...],
        tuple[_InformationCandidate, ...],
        tuple[ProtectedInformationGuard, ...],
    ]:
        latest: dict[
            int, tuple[tuple[int, int, int], CharacterKnowledgeEventRecord]
        ] = {}
        for event in self._repository.knowledge_events(work_id, character_id):
            order = self._repository.get_episode_order(work_id, event.episode_id)
            if (
                order is None
                or order > target_order
                or event.knowledge_state not in KNOWN_STATES
            ):
                continue
            rank = (*order, event.id)
            current = latest.get(event.information_item_id)
            if current is None or rank > current[0]:
                latest[event.information_item_id] = (rank, event)

        known: list[ParticipantKnownInformation] = []
        candidates: list[_InformationCandidate] = []
        guards: list[ProtectedInformationGuard] = []
        for _, event in sorted(latest.values(), key=lambda value: value[0]):
            item = self._repository.information(work_id, event.information_item_id)
            if item is None or item.canon_status == "deprecated":
                continue
            disclosure = self._repository.disclosure(work_id, item.id)
            boundary = self._disclosure_order(work_id, disclosure)
            if boundary is None or boundary > target_order:
                guards.append(
                    _guard_for(
                        item,
                        disclosure,
                        boundary,
                        event.character_id,
                        event.knowledge_state,
                    )
                )
                continue
            safe_item = _safe_information(item)
            known.append(
                ParticipantKnownInformation(
                    information_item_id=item.id,
                    knowledge_state=event.knowledge_state,
                    source_episode_id=event.episode_id,
                    statement=item.statement,
                    truth_status=item.truth_status,
                    canon_status=item.canon_status,
                )
            )
            candidates.append(
                _InformationCandidate(
                    item=safe_item, direct_reference=False, disclosure_order=boundary
                )
            )
        return tuple(known), tuple(candidates), tuple(guards)

    def _reader_context(
        self,
        work_id: int,
        target_order: tuple[int, int],
        outline: EpisodeOutline,
        participant_candidates: Sequence[_InformationCandidate],
    ) -> tuple[ReaderContext, int]:
        candidates: dict[int, _InformationCandidate] = {}
        reveal: dict[int, SafeInformationItem] = {}
        for item in outline.references.information:
            disclosure = self._repository.disclosure(work_id, item.id)
            boundary = self._disclosure_order(work_id, disclosure)
            if boundary is None:
                continue
            if boundary == target_order:
                reveal[item.id] = item
            elif boundary < target_order:
                candidates[item.id] = _InformationCandidate(
                    item=item, direct_reference=True, disclosure_order=boundary
                )
        for candidate in participant_candidates:
            if candidate.disclosure_order == target_order:
                reveal[candidate.item.id] = candidate.item
            elif candidate.disclosure_order < target_order:
                current = candidates.get(candidate.item.id)
                if current is None or candidate.direct_reference:
                    candidates[candidate.item.id] = candidate
        selected = sorted(
            candidates.values(),
            key=lambda candidate: (
                not candidate.direct_reference,
                -candidate.item.importance,
                -candidate.disclosure_order[0],
                -candidate.disclosure_order[1],
                candidate.item.id,
            ),
        )[:INFORMATION_ITEMS_MAX]
        return (
            ReaderContext(
                known_before_episode=tuple(candidate.item for candidate in selected),
                reveal_this_episode=tuple(
                    reveal[item_id] for item_id in sorted(reveal)
                ),
            ),
            max(0, len(candidates) - len(selected)),
        )

    def _disclosure_order(
        self, work_id: int, disclosure: ReaderDisclosureRecord | None
    ) -> tuple[int, int] | None:
        if disclosure is None:
            return None
        return self._repository.get_episode_order(work_id, disclosure.episode_id)

    def _limit_participant_information(
        self,
        participants: Sequence[ContextParticipant],
        reader_context: ReaderContext,
    ) -> tuple[ContextParticipant, ...]:
        allowed_ids = {
            item.id
            for item in (
                *reader_context.known_before_episode,
                *reader_context.reveal_this_episode,
            )
        }
        return tuple(
            ContextParticipant(
                profile=participant.profile,
                effective_state=participant.effective_state,
                effective_relationships=participant.effective_relationships,
                known_information=tuple(
                    item
                    for item in participant.known_information
                    if item.information_item_id in allowed_ids
                ),
            )
            for participant in participants
        )

    def _recent_context(
        self, work_id: int, target_order: tuple[int, int]
    ) -> tuple[RecentContext, int, bool]:
        all_previous = self._previous_episodes(work_id, target_order)
        previous = all_previous[-PREVIOUS_SUMMARIES_MAX:]
        summaries = tuple(
            PreviousEpisodeSummary(
                episode_id=episode.id,
                chapter_position=order[0],
                episode_position=order[1],
                title=episode.title,
                summary=episode.summary,
            )
            for episode, order in previous
        )
        previous_draft = (
            self._repository.latest_draft(work_id, all_previous[-1][0].id)
            if all_previous
            else None
        )
        body = "" if previous_draft is None else previous_draft.body
        return (
            RecentContext(
                previous_episode_summaries=summaries,
                previous_draft_tail=body[-PREVIOUS_DRAFT_TAIL_CHARS:],
            ),
            max(0, len(all_previous) - len(summaries)),
            len(body) > PREVIOUS_DRAFT_TAIL_CHARS,
        )

    def _previous_episodes(
        self, work_id: int, target_order: tuple[int, int]
    ) -> list[tuple[EpisodeRecord, tuple[int, int]]]:
        previous: list[tuple[EpisodeRecord, tuple[int, int]]] = []
        for episode in self._repository.list_episodes(work_id):
            if episode.canon_status == "deprecated":
                continue
            order = self._repository.get_episode_order(work_id, episode.id)
            if order is not None and order < target_order:
                previous.append((episode, order))
        return previous

    def _merge_guards(
        self,
        outline_guards: Sequence[ProtectedInformationGuard],
        participant_guards: Sequence[ProtectedInformationGuard],
    ) -> tuple[ProtectedInformationGuard, ...]:
        unique: dict[tuple[int, int | None], ProtectedInformationGuard] = {}
        for guard in (*outline_guards, *participant_guards):
            unique[(guard.information_item_id, guard.character_id)] = guard
        return tuple(
            unique[key]
            for key in sorted(unique, key=lambda value: (value[0], value[1] or 0))
        )

    def _context_meta(
        self,
        *,
        target_order: tuple[int, int],
        world_facts_returned: int,
        world_facts_total: int,
        timeline_events_returned: int,
        timeline_events_total: int,
        information_returned: int,
        information_total: int,
        previous_returned: int,
        previous_total: int,
        previous_draft_tail: int,
        draft_truncated: bool,
        guard_count: int,
    ) -> dict[str, object]:
        return {
            "narrative_position": {
                "chapter_position": target_order[0],
                "episode_position": target_order[1],
            },
            "limits": {
                "previous_episode_summaries": PREVIOUS_SUMMARIES_MAX,
                "previous_draft_tail_chars": PREVIOUS_DRAFT_TAIL_CHARS,
                "world_facts_max": WORLD_FACTS_MAX,
                "timeline_events_max": TIMELINE_EVENTS_MAX,
                "information_items_max": INFORMATION_ITEMS_MAX,
            },
            "returned_counts": {
                "previous_episode_summaries": previous_returned,
                "previous_draft_tail_chars": previous_draft_tail,
                "world_facts": world_facts_returned,
                "timeline_events": timeline_events_returned,
                "information_items": information_returned,
                "protected_information_guards": guard_count,
            },
            "omitted_counts": {
                "previous_episode_summaries": max(
                    0, previous_total - previous_returned
                ),
                "world_facts": max(0, world_facts_total - world_facts_returned),
                "timeline_events": max(
                    0, timeline_events_total - timeline_events_returned
                ),
                "information_items": max(0, information_total - INFORMATION_ITEMS_MAX),
            },
            "truncated": {
                "world_facts": world_facts_total > WORLD_FACTS_MAX,
                "timeline_events": timeline_events_total > TIMELINE_EVENTS_MAX,
                "information_items": information_total > INFORMATION_ITEMS_MAX,
                "previous_draft_tail": draft_truncated,
            },
        }


def _parse_foreshadowing(value: str) -> tuple[object, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "foreshadowing_notes must be valid JSON", field="foreshadowing_notes"
        ) from exc
    if not isinstance(parsed, list):
        raise ValidationError(
            "foreshadowing_notes must be a JSON array", field="foreshadowing_notes"
        )
    return tuple(parsed)


def _safe_information(item: InformationItemRecord) -> SafeInformationItem:
    return SafeInformationItem(
        id=item.id,
        statement=item.statement,
        truth_status=item.truth_status,
        canon_status=item.canon_status,
        importance=item.importance,
    )


def _safe_relationship(
    record: RelationshipRecord, character_id: int
) -> EffectiveRelationship:
    related_id = (
        record.target_character_id
        if record.source_character_id == character_id
        else record.source_character_id
    )
    return EffectiveRelationship(
        relationship_id=record.id,
        related_character_id=related_id,
        relationship_type=record.relationship_type,
        description=record.description,
        canon_status=record.canon_status,
    )


def _guard_for(
    item: InformationItemRecord,
    disclosure: ReaderDisclosureRecord | None,
    boundary: tuple[int, int] | None,
    character_id: int | None = None,
    knowledge_state: str | None = None,
) -> ProtectedInformationGuard:
    guard_text = item.authoring_guard
    if not guard_text or item.statement in guard_text:
        guard_text = GENERIC_GUARD
    return ProtectedInformationGuard(
        information_item_id=item.id,
        reason=(
            "reader_disclosure_after_target"
            if boundary is not None
            else "reader_disclosure_missing"
        ),
        guard_text=guard_text,
        reveal_boundary=(
            None
            if disclosure is None or boundary is None
            else RevealBoundary(
                episode_id=disclosure.episode_id,
                chapter_position=boundary[0],
                episode_position=boundary[1],
            )
        ),
        character_id=character_id,
        knowledge_state=knowledge_state,
    )
