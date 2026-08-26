from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from novel_mcp.errors import WorkScopeError
from novel_mcp.phase3_acceptance_seed import ActiveProbeScenario
from novel_mcp.repositories.context_repository import ContextRepository
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.outline_service import OutlineService
from novel_mcp.tool_errors import json_value


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
        return _failed_results()
    target_order = repository.get_episode_order(work.id, episode_id)
    future_order = repository.get_episode_order(work.id, scenario.future_episode_id)

    context_bounds_ok = _active_bounds_ok(
        context, current_reveal_item_id=scenario.current_reveal_item_id
    )
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
    other_work_ok = (
        bool(other_work_exists)
        and scenario.other_episode_title not in serialized_context
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
    return not _keys(value) & {
        "private_notes",
        "profile_json",
        "death_date",
        "details_json",
        "notes_json",
    }


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for item in value.values() for key in _keys(item)
        }
    if isinstance(value, (list, tuple)):
        return {key for item in value for key in _keys(item)}
    return set()


def _active_bounds_ok(context: Any, *, current_reveal_item_id: int) -> bool:
    meta = context.context_meta
    truncated = meta.get("truncated", {})
    reveal_ids = {
        item.id for item in context.reader_context.reveal_this_episode
    }
    return (
        current_reveal_item_id in reveal_ids
        and len(context.recent_context.previous_episode_summaries) == 2
        and len(context.recent_context.previous_draft_tail) == 4000
        and len(context.world_facts) == 30
        and len(context.timeline_events) == 30
        and len(context.reader_context.known_before_episode) == 50
        and truncated.get("world_facts") is True
        and truncated.get("timeline_events") is True
        and truncated.get("information_items") is True
        and truncated.get("previous_draft_tail") is True
    )


def _failed_results() -> ProbeResults:
    return ProbeResults(
        context_bounds_ok=False,
        future_episode_ok=False,
        future_state_ok=False,
        future_knowledge_ok=False,
        future_disclosure_ok=False,
        deprecated_ok=False,
        other_work_ok=False,
        private_notes_ok=False,
        profile_json_ok=False,
        protected_statement_ok=False,
        guard_present=False,
    )


def _serialized(value: Any) -> str:
    return json.dumps(
        json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
