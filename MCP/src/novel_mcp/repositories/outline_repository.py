from __future__ import annotations

import sqlite3

from novel_mcp.repositories.character_repository import (
    CharacterRecord,
    CharacterRepository,
)
from novel_mcp.repositories.disclosure_repository import (
    DisclosureRepository,
    ReaderDisclosureRecord,
)
from novel_mcp.repositories.episode_reference_repository import (
    EpisodeReferenceRecord,
    EpisodeReferenceRepository,
)
from novel_mcp.repositories.information_repository import (
    InformationItemRecord,
    InformationRepository,
)
from novel_mcp.repositories.narrative_repository import (
    EpisodeRecord,
    NarrativeRepository,
    SceneRecord,
)
from novel_mcp.repositories.timeline_repository import (
    TimelineEventRecord,
    TimelineRepository,
)
from novel_mcp.repositories.world_fact_repository import (
    WorldFactRecord,
    WorldFactRepository,
)


class OutlineRepository:
    """Read-only composition of the repositories needed for an outline."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._narrative = NarrativeRepository(connection)
        self._references = EpisodeReferenceRepository(connection)
        self._characters = CharacterRepository(connection)
        self._world_facts = WorldFactRepository(connection)
        self._timeline = TimelineRepository(connection)
        self._information = InformationRepository(connection, force_fallback=True)
        self._disclosures = DisclosureRepository(connection)

    def get_episode(self, work_id: int, episode_id: int) -> EpisodeRecord | None:
        return self._narrative.get_episode(work_id=work_id, episode_id=episode_id)

    def get_episode_work_id(self, episode_id: int) -> int | None:
        return self._narrative.get_episode_work_id(episode_id)

    def get_episode_order(
        self, work_id: int, episode_id: int
    ) -> tuple[int, int] | None:
        return self._narrative.get_episode_narrative_order(
            work_id=work_id, episode_id=episode_id
        )

    def list_scenes(self, work_id: int, episode_id: int) -> tuple[SceneRecord, ...]:
        return self._narrative.list_scenes(work_id=work_id, episode_id=episode_id)

    def list_references(
        self, work_id: int, episode_id: int
    ) -> tuple[EpisodeReferenceRecord, ...]:
        return self._references.list(
            work_id=work_id, episode_id=episode_id, reference_type=None
        )

    def get_character(self, work_id: int, character_id: int) -> CharacterRecord | None:
        return self._characters.get(work_id=work_id, character_id=character_id)

    def get_world_fact(self, work_id: int, fact_id: int) -> WorldFactRecord | None:
        return self._world_facts.get(work_id=work_id, fact_id=fact_id)

    def get_timeline_event(
        self, work_id: int, event_id: int
    ) -> TimelineEventRecord | None:
        return self._timeline.get(work_id=work_id, event_id=event_id)

    def get_information(
        self, work_id: int, item_id: int
    ) -> InformationItemRecord | None:
        return self._information.get(work_id=work_id, item_id=item_id)

    def get_disclosure(
        self, work_id: int, item_id: int
    ) -> ReaderDisclosureRecord | None:
        return self._disclosures.get(work_id=work_id, information_item_id=item_id)
