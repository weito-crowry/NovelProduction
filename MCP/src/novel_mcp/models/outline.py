from __future__ import annotations

from dataclasses import dataclass

from novel_mcp.repositories.narrative_repository import EpisodeRecord, SceneRecord


@dataclass(frozen=True, slots=True)
class SafeCharacterProfile:
    id: int
    character_key: str
    display_name: str
    entity_type: str
    description: str
    birth_date: str | None
    physical_description: str
    occupation: str
    core_beliefs: str
    goals: str
    fears: str
    personality: str
    speech_style: str
    ai_attitude: str
    genetic_modification_attitude: str
    canon_status: str


@dataclass(frozen=True, slots=True)
class OutlineParticipant:
    profile: SafeCharacterProfile
    role: str


@dataclass(frozen=True, slots=True)
class SafeWorldFact:
    id: int
    topic_key: str
    category: str
    title: str
    statement: str
    valid_from: str | None
    valid_to: str | None
    canon_status: str
    importance: int


@dataclass(frozen=True, slots=True)
class SafeTimelineEvent:
    id: int
    event_key: str
    time_start: str | None
    time_end: str | None
    date_precision: str
    date_display: str
    title: str
    description: str
    category: str
    location_world_fact_id: int | None
    cause_summary: str
    consequence_summary: str
    canon_status: str
    importance: int


@dataclass(frozen=True, slots=True)
class SafeInformationItem:
    id: int
    statement: str
    truth_status: str
    canon_status: str
    importance: int


@dataclass(frozen=True, slots=True)
class RevealBoundary:
    episode_id: int
    chapter_position: int
    episode_position: int


@dataclass(frozen=True, slots=True)
class ProtectedInformationGuard:
    information_item_id: int
    reason: str
    guard_text: str
    reveal_boundary: RevealBoundary | None
    character_id: int | None = None
    knowledge_state: str | None = None


@dataclass(frozen=True, slots=True)
class OutlineReferences:
    world_facts: tuple[SafeWorldFact, ...]
    timeline_events: tuple[SafeTimelineEvent, ...]
    information: tuple[SafeInformationItem, ...]


@dataclass(frozen=True, slots=True)
class EpisodeOutline:
    episode: EpisodeRecord
    scenes: tuple[SceneRecord, ...]
    participants: tuple[OutlineParticipant, ...]
    references: OutlineReferences
    protected_information_guards: tuple[ProtectedInformationGuard, ...]
