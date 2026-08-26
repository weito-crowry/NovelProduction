from __future__ import annotations

import sqlite3

from novel_mcp.repositories.character_state_repository import (
    CharacterStateRecord,
    CharacterStateRepository,
)
from novel_mcp.repositories.disclosure_repository import (
    DisclosureRepository,
    ReaderDisclosureRecord,
)
from novel_mcp.repositories.draft_repository import DraftRecord, DraftRepository
from novel_mcp.repositories.information_repository import (
    InformationItemRecord,
    InformationRepository,
)
from novel_mcp.repositories.knowledge_repository import (
    CharacterKnowledgeEventRecord,
    KnowledgeRepository,
)
from novel_mcp.repositories.narrative_repository import (
    EpisodeRecord,
    NarrativeRepository,
)
from novel_mcp.repositories.relationship_repository import (
    RelationshipRecord,
    RelationshipRepository,
)


class ContextRepository:
    """Read-only data access for the episode context composition."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection
        self._narrative = NarrativeRepository(connection)
        self._states = CharacterStateRepository(connection)
        self._relationships = RelationshipRepository(connection)
        self._knowledge = KnowledgeRepository(connection)
        self._information = InformationRepository(connection, force_fallback=True)
        self._disclosures = DisclosureRepository(connection)
        self._drafts = DraftRepository(connection)

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

    def list_episodes(self, work_id: int) -> tuple[EpisodeRecord, ...]:
        rows = self._db.execute(
            """
            SELECT e.id, e.work_id, e.chapter_id, e.position, e.title, e.summary,
                   e.purpose, e.foreshadowing_notes_json, e.canon_status,
                   e.production_status, e.version, e.created_at, e.updated_at
            FROM episodes AS e
            JOIN chapters AS c ON c.work_id = e.work_id AND c.id = e.chapter_id
            WHERE e.work_id = ?
            ORDER BY c.position, e.position, e.id
            """,
            (work_id,),
        ).fetchall()
        return tuple(EpisodeRecord(*row) for row in rows)

    def effective_state(
        self, work_id: int, character_id: int, episode_id: int
    ) -> CharacterStateRecord | None:
        return self._states.effective(
            work_id=work_id, character_id=character_id, episode_id=episode_id
        )

    def relationships(self, work_id: int) -> tuple[RelationshipRecord, ...]:
        return self._relationships.list_all(work_id=work_id)

    def knowledge_events(
        self, work_id: int, character_id: int
    ) -> tuple[CharacterKnowledgeEventRecord, ...]:
        return self._knowledge.list_for_character(
            work_id=work_id, character_id=character_id
        )

    def information(
        self, work_id: int, information_item_id: int
    ) -> InformationItemRecord | None:
        return self._information.get(work_id=work_id, item_id=information_item_id)

    def disclosure(
        self, work_id: int, information_item_id: int
    ) -> ReaderDisclosureRecord | None:
        return self._disclosures.get(
            work_id=work_id, information_item_id=information_item_id
        )

    def latest_draft(self, work_id: int, episode_id: int) -> DraftRecord | None:
        return self._drafts.latest(work_id=work_id, episode_id=episode_id)
