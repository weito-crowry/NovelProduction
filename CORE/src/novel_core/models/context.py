from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_core.models.outline import (
    ProtectedInformationGuard,
    SafeCharacterProfile,
    SafeInformationItem,
    SafeTimelineEvent,
    SafeWorldFact,
)
from novel_core.repositories.narrative_repository import EpisodeRecord, SceneRecord


@dataclass(frozen=True, slots=True)
class EffectiveCharacterState:
    state_id: int
    source_episode_id: int
    physical_state: str
    emotional_state: str
    beliefs: Any
    location_world_fact_id: int | None


@dataclass(frozen=True, slots=True)
class EffectiveRelationship:
    relationship_id: int
    related_character_id: int
    relationship_type: str
    description: str
    canon_status: str


@dataclass(frozen=True, slots=True)
class ParticipantKnownInformation:
    information_item_id: int
    knowledge_state: str
    source_episode_id: int
    statement: str | None
    truth_status: str | None
    canon_status: str


@dataclass(frozen=True, slots=True)
class ContextParticipant:
    profile: SafeCharacterProfile
    effective_state: EffectiveCharacterState | None
    effective_relationships: tuple[EffectiveRelationship, ...]
    known_information: tuple[ParticipantKnownInformation, ...]


@dataclass(frozen=True, slots=True)
class ReaderContext:
    known_before_episode: tuple[SafeInformationItem, ...]
    reveal_this_episode: tuple[SafeInformationItem, ...]


@dataclass(frozen=True, slots=True)
class PreviousEpisodeSummary:
    episode_id: int
    chapter_position: int
    episode_position: int
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class RecentContext:
    previous_episode_summaries: tuple[PreviousEpisodeSummary, ...]
    previous_draft_context_html: str


@dataclass(frozen=True, slots=True)
class EpisodeContext:
    episode: EpisodeRecord
    scenes: tuple[SceneRecord, ...]
    participants: tuple[ContextParticipant, ...]
    world_facts: tuple[SafeWorldFact, ...]
    timeline_events: tuple[SafeTimelineEvent, ...]
    reader_context: ReaderContext
    protected_information_guards: tuple[ProtectedInformationGuard, ...]
    recent_context: RecentContext
    foreshadowing_notes: tuple[object, ...]
    context_meta: dict[str, object]
