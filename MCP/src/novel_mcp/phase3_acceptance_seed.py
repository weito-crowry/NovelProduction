from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from novel_core.repositories.context_repository import ContextRepository
from novel_core.repositories.work_repository import WorkRepository
from novel_core.services.character_service import CharacterService
from novel_core.services.character_state_service import CharacterStateService
from novel_core.services.disclosure_service import DisclosureService
from novel_core.services.draft_service import DraftService
from novel_core.services.episode_reference_service import EpisodeReferenceService
from novel_core.services.information_service import InformationService
from novel_core.services.knowledge_service import KnowledgeService
from novel_core.services.narrative_service import NarrativeService
from novel_core.services.timeline_service import TimelineService
from novel_core.services.world_fact_service import WorldFactService


@dataclass(frozen=True, slots=True)
class ActiveProbeScenario:
    future_episode_id: int
    future_episode_title: str
    future_state_sentinel: str
    future_belief_sentinel: str
    future_knowledge_statement: str
    future_disclosure_item_id: int
    future_disclosure_statement: str
    deprecated_statement: str
    private_notes_sentinel: str
    profile_json_sentinel: str
    current_reveal_item_id: int
    other_episode_id: int
    other_episode_title: str


def seed_active_probes(
    database: sqlite3.Connection, *, episode_id: int
) -> ActiveProbeScenario:
    work = WorkRepository(database).get()
    if work is None:
        raise RuntimeError("acceptance requires a configured work")
    repository = ContextRepository(database)
    target = repository.get_episode(work.id, episode_id)
    if target is None:
        raise RuntimeError("acceptance target episode is missing")

    narrative = NarrativeService(database)
    references = EpisodeReferenceService(database)
    information = InformationService(database)
    disclosures = DisclosureService(database)
    characters = CharacterService(database)
    states = CharacterStateService(database)
    knowledge = KnowledgeService(database)
    world = WorldFactService(database)
    timeline = TimelineService(database)
    drafts = DraftService(database)

    previous = [
        narrative.create_episode(
            target.chapter_id,
            f"PHASE3_ACCEPTANCE_PREVIOUS_{index}",
            summary=f"acceptance previous summary {index}",
        )
        for index in range(3)
    ]
    current = repository.get_episode(work.id, episode_id)
    if current is None:
        raise RuntimeError("acceptance target disappeared")
    siblings = [
        item
        for item in repository.list_episodes(work.id)
        if item.chapter_id == current.chapter_id
    ]
    last_position = max(item.position for item in siblings)
    if current.position != last_position:
        narrative.reorder_episode(current.id, last_position, current.version)

    immediate_previous = previous[-1]
    drafts.save_draft(immediate_previous.id, "P" * 5001, source_agent="acceptance")

    future_episode_title = "SECRET_FUTURE_EPISODE_TITLE_PHASE3"
    future = narrative.create_episode(target.chapter_id, future_episode_title)

    private_notes_sentinel = "SECRET_PRIVATE_NOTE_PHASE3"
    profile_json_sentinel = "SECRET_PROFILE_JSON_PHASE3"
    participant = characters.create(
        "Acceptance Character",
        character_key=f"phase3-acceptance-character-{episode_id}",
        private_notes=private_notes_sentinel,
        profile_json=json.dumps({"secret": profile_json_sentinel}),
    )
    references.add(episode_id, "character", participant.id)

    future_state_sentinel = "SECRET_FUTURE_STATE_PHASE3"
    future_belief_sentinel = "SECRET_FUTURE_BELIEF_PHASE3"
    states.set_state(
        participant.id,
        future.id,
        physical_state=future_state_sentinel,
        beliefs_json={"secret": future_belief_sentinel},
    )

    future_knowledge = information.create_information("SECRET_FUTURE_KNOWLEDGE_PHASE3")
    disclosures.set_reader_disclosure(future_knowledge.id, immediate_previous.id)
    knowledge.set_character_knowledge(
        participant.id, future_knowledge.id, future.id, "knows"
    )

    future_disclosure_statement = "SECRET_FUTURE_DISCLOSURE_PHASE3"
    protected = information.create_information(
        future_disclosure_statement,
        authoring_guard="Keep the protected acceptance plot point undisclosed.",
    )
    references.add(episode_id, "information", protected.id)
    disclosures.set_reader_disclosure(protected.id, future.id)

    current_reveal = information.create_information("PHASE3_CURRENT_REVEAL")
    disclosures.set_reader_disclosure(current_reveal.id, episode_id)

    deprecated_statement = "SECRET_DEPRECATED_INFORMATION_PHASE3"
    deprecated = information.create_information(deprecated_statement)
    references.add(episode_id, "information", deprecated.id)
    canonical = information.update_information(
        deprecated.id,
        deprecated.version,
        canon_status="canon",
        reason="acceptance canon probe",
    )
    information.update_information(
        deprecated.id,
        canonical.version,
        canon_status="deprecated",
        reason="acceptance deprecation probe",
    )

    for index in range(60):
        item = information.create_information(
            f"PHASE3_READER_SAFE_INFORMATION_{index}", importance=index
        )
        disclosures.set_reader_disclosure(item.id, immediate_previous.id)
        references.add(episode_id, "information", item.id)

    for index in range(40):
        fact = world.create(
            f"PHASE3_WORLD_FACT_{index}",
            topic_key=f"phase3-acceptance-fact-{episode_id}-{index}",
            title=f"Acceptance Fact {index}",
            importance=index,
        )
        references.add(episode_id, "world_fact", fact.id)
        event = timeline.create_event(
            title=f"PHASE3_TIMELINE_EVENT_{index}", importance=index
        )
        references.add(episode_id, "timeline_event", event.id)

    other_slug = f"phase3-acceptance-other-{episode_id}"
    database.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        (other_slug, "Acceptance Other Work"),
    )
    other_work_id = database.execute(
        "SELECT id FROM works WHERE slug = ?", (other_slug,)
    ).fetchone()[0]
    database.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, ?, ?)",
        (other_work_id, 1, "Acceptance Other Chapter"),
    )
    other_chapter_id = database.execute(
        "SELECT id FROM chapters WHERE work_id = ?", (other_work_id,)
    ).fetchone()[0]
    other_episode_title = "SECRET_OTHER_WORK_EPISODE_PHASE3"
    database.execute(
        "INSERT INTO episodes (work_id, chapter_id, position, title) "
        "VALUES (?, ?, ?, ?)",
        (other_work_id, other_chapter_id, 1, other_episode_title),
    )
    other_episode_id = database.execute(
        "SELECT id FROM episodes WHERE work_id = ?", (other_work_id,)
    ).fetchone()[0]
    database.commit()

    return ActiveProbeScenario(
        future_episode_id=future.id,
        future_episode_title=future_episode_title,
        future_state_sentinel=future_state_sentinel,
        future_belief_sentinel=future_belief_sentinel,
        future_knowledge_statement=future_knowledge.statement,
        future_disclosure_item_id=protected.id,
        future_disclosure_statement=future_disclosure_statement,
        deprecated_statement=deprecated_statement,
        private_notes_sentinel=private_notes_sentinel,
        profile_json_sentinel=profile_json_sentinel,
        current_reveal_item_id=current_reveal.id,
        other_episode_id=other_episode_id,
        other_episode_title=other_episode_title,
    )
