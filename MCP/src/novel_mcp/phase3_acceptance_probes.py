from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from novel_mcp.errors import WorkScopeError
from novel_mcp.repositories.context_repository import ContextRepository
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.character_state_service import CharacterStateService
from novel_mcp.services.disclosure_service import DisclosureService
from novel_mcp.services.draft_service import DraftService
from novel_mcp.services.episode_reference_service import EpisodeReferenceService
from novel_mcp.services.information_service import InformationService
from novel_mcp.services.knowledge_service import KnowledgeService
from novel_mcp.services.narrative_service import NarrativeService
from novel_mcp.services.outline_service import OutlineService
from novel_mcp.services.timeline_service import TimelineService
from novel_mcp.services.world_fact_service import WorldFactService
from novel_mcp.tool_errors import json_value


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


@dataclass(frozen=True, slots=True)
class ProbeResults:
    context_bounds_ok: bool
    future_episode_ok: bool
    future_state_ok: bool
    future_knowledge_ok: bool
    future_disclosure_ok: bool
    deprecated_ok: bool
    other_work_ok: bool
    private_notes_ok: bool
    profile_json_ok: bool
    protected_statement_ok: bool
    guard_present: bool


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


def evaluate_active_probes(
    database: sqlite3.Connection,
    *,
    episode_id: int,
    context: Any,
    context_payload: Any,
    outline_payload: Any,
    scenario: ActiveProbeScenario,
) -> ProbeResults:
    serialized_context = _serialized(context_payload)
    serialized_outline = _serialized(outline_payload)
    repository = ContextRepository(database)
    work = WorkRepository(database).get()
    if work is None or context is None:
        return ProbeResults(*(False for _ in range(11)))
    target_order = repository.get_episode_order(work.id, episode_id)
    future_order = repository.get_episode_order(work.id, scenario.future_episode_id)

    context_bounds_ok = _active_bounds_ok(context)
    future_episode_ok = (
        target_order is not None
        and future_order is not None
        and future_order > target_order
        and scenario.future_episode_title not in serialized_context
    )
    future_state_exists = database.execute(
        "SELECT 1 FROM character_states WHERE episode_id = ? "
        "AND (physical_state = ? OR beliefs_json LIKE ?) LIMIT 1",
        (
            scenario.future_episode_id,
            scenario.future_state_sentinel,
            f"%{scenario.future_belief_sentinel}%",
        ),
    ).fetchone()
    future_state_ok = bool(future_state_exists) and all(
        sentinel not in serialized_context
        for sentinel in (
            scenario.future_state_sentinel,
            scenario.future_belief_sentinel,
        )
    )
    future_knowledge_exists = database.execute(
        "SELECT 1 FROM character_knowledge_events AS k "
        "JOIN information_items AS i ON i.id = k.information_item_id "
        "WHERE k.episode_id = ? AND i.statement = ? LIMIT 1",
        (scenario.future_episode_id, scenario.future_knowledge_statement),
    ).fetchone()
    future_knowledge_ok = (
        bool(future_knowledge_exists)
        and scenario.future_knowledge_statement not in serialized_context
    )
    future_disclosure = repository.disclosure(
        work.id, scenario.future_disclosure_item_id
    )
    disclosure_order = (
        None
        if future_disclosure is None
        else repository.get_episode_order(work.id, future_disclosure.episode_id)
    )
    guard_ids = {
        guard.information_item_id for guard in context.protected_information_guards
    }
    future_disclosure_ok = (
        future_disclosure is not None
        and target_order is not None
        and disclosure_order is not None
        and disclosure_order > target_order
        and scenario.future_disclosure_statement not in serialized_context
        and scenario.future_disclosure_item_id in guard_ids
        and strict_safe_disclosures(database, episode_id, context)
    )
    deprecated_exists = database.execute(
        "SELECT 1 FROM information_items WHERE statement = ? "
        "AND canon_status = 'deprecated' LIMIT 1",
        (scenario.deprecated_statement,),
    ).fetchone()
    deprecated_ok = (
        bool(deprecated_exists)
        and scenario.deprecated_statement not in serialized_context
        and not has_deprecated(context_payload)
    )
    other_work_exists = database.execute(
        "SELECT 1 FROM episodes WHERE id = ? AND work_id != ?",
        (scenario.other_episode_id, work.id),
    ).fetchone()
    other_work_ok = bool(other_work_exists) and all(
        sentinel not in serialized_context
        for sentinel in (scenario.other_episode_title,)
    )
    try:
        OutlineService(database).get_episode_outline(scenario.other_episode_id)
    except WorkScopeError:
        pass
    except Exception:
        other_work_ok = False
    else:
        other_work_ok = False
    private_notes_ok = (
        database.execute(
            "SELECT 1 FROM characters WHERE private_notes = ? LIMIT 1",
            (scenario.private_notes_sentinel,),
        ).fetchone()
        is not None
        and scenario.private_notes_sentinel not in serialized_context
        and scenario.private_notes_sentinel not in serialized_outline
    )
    profile_json_ok = (
        database.execute(
            "SELECT 1 FROM characters WHERE profile_json LIKE ? LIMIT 1",
            (f"%{scenario.profile_json_sentinel}%",),
        ).fetchone()
        is not None
        and scenario.profile_json_sentinel not in serialized_context
        and scenario.profile_json_sentinel not in serialized_outline
    )
    protected_statement_ok = (
        scenario.future_disclosure_statement not in serialized_context
        and scenario.future_disclosure_statement not in serialized_outline
    )
    guard_present = scenario.future_disclosure_item_id in guard_ids
    return ProbeResults(
        context_bounds_ok=context_bounds_ok,
        future_episode_ok=future_episode_ok,
        future_state_ok=future_state_ok,
        future_knowledge_ok=future_knowledge_ok,
        future_disclosure_ok=future_disclosure_ok,
        deprecated_ok=deprecated_ok,
        other_work_ok=other_work_ok,
        private_notes_ok=private_notes_ok,
        profile_json_ok=profile_json_ok,
        protected_statement_ok=protected_statement_ok,
        guard_present=guard_present,
    )


def strict_safe_disclosures(
    database: sqlite3.Connection, episode_id: int, context: Any
) -> bool:
    if context is None:
        return False
    repository = ContextRepository(database)
    work = WorkRepository(database).get()
    if work is None:
        return False
    target = repository.get_episode_order(work.id, episode_id)
    if target is None:
        return False
    safe_items = (
        *context.reader_context.known_before_episode,
        *context.reader_context.reveal_this_episode,
    )
    for item in safe_items:
        disclosure = repository.disclosure(work.id, item.id)
        if disclosure is None:
            return False
        boundary = repository.get_episode_order(work.id, disclosure.episode_id)
        if boundary is None or boundary > target:
            return False
    return True


def has_deprecated(value: Any) -> bool:
    if is_dataclass(value) and not isinstance(value, type):
        return has_deprecated(asdict(value))
    if isinstance(value, dict):
        if value.get("canon_status") == "deprecated":
            return True
        return any(has_deprecated(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_deprecated(item) for item in value)
    return bool(
        hasattr(value, "canon_status") and value.canon_status == "deprecated"
    )


def safe_keys(value: Any) -> bool:
    return not keys(value) & {
        "private_notes",
        "profile_json",
        "death_date",
        "details_json",
        "notes_json",
    }


def keys_absent(value: Any, forbidden: set[str]) -> bool:
    return not keys(value) & forbidden


def keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keys(item)}
    if isinstance(value, (list, tuple)):
        return {key for item in value for key in keys(item)}
    return set()


def _active_bounds_ok(context: Any) -> bool:
    meta = context.context_meta
    truncated = meta.get("truncated", {})
    return (
        len(context.recent_context.previous_episode_summaries) == 2
        and len(context.recent_context.previous_draft_tail) == 4000
        and len(context.world_facts) == 30
        and len(context.timeline_events) == 30
        and len(context.reader_context.known_before_episode) == 50
        and truncated.get("world_facts") is True
        and truncated.get("timeline_events") is True
        and truncated.get("information_items") is True
        and truncated.get("previous_draft_tail") is True
    )


def _serialized(value: Any) -> str:
    return json.dumps(json_value(value), ensure_ascii=False, sort_keys=True, default=str)
