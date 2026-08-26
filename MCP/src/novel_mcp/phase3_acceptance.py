from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, fields
from typing import Any

from novel_mcp.errors import VersionConflictError, WorkScopeError
from novel_mcp.phase2_tool_descriptions import PHASE2_TOOL_DESCRIPTIONS
from novel_mcp.phase3_tool_descriptions import PHASE3_TOOL_DESCRIPTIONS
from novel_mcp.repositories.context_repository import ContextRepository
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.context_service import (
    INFORMATION_ITEMS_MAX,
    PREVIOUS_DRAFT_TAIL_CHARS,
    PREVIOUS_SUMMARIES_MAX,
    TIMELINE_EVENTS_MAX,
    WORLD_FACTS_MAX,
    ContextService,
)
from novel_mcp.services.draft_service import DraftService
from novel_mcp.services.outline_service import OutlineService
from novel_mcp.tool_descriptions import TOOL_DESCRIPTIONS
from novel_mcp.tool_errors import json_value


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    migration_sequence_ok: bool
    draft_append_only: bool
    draft_parent_cas_ok: bool
    draft_hash_ok: bool
    outline_safe: bool
    context_read_only: bool
    context_bounds_ok: bool
    future_episode_leakage_blocked: bool
    future_state_leakage_blocked: bool
    future_knowledge_leakage_blocked: bool
    future_disclosure_leakage_blocked: bool
    deprecated_canon_leakage_blocked: bool
    other_work_leakage_blocked: bool
    private_notes_leakage_blocked: bool
    profile_json_leakage_blocked: bool
    protected_statement_leakage_blocked: bool
    guard_present: bool
    tool_inventory_ok: bool
    writing_ready: bool

    @property
    def drafts_are_append_only(self) -> bool:
        return self.draft_append_only

    @property
    def context_is_bounded(self) -> bool:
        return self.context_bounds_ok

    @property
    def future_leakage_is_blocked(self) -> bool:
        return all(
            (
                self.future_episode_leakage_blocked,
                self.future_state_leakage_blocked,
                self.future_knowledge_leakage_blocked,
                self.future_disclosure_leakage_blocked,
            )
        )

    @property
    def invariants(self) -> dict[str, bool]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "writing_ready"
        }


def run_phase3_acceptance(
    database: sqlite3.Connection, *, episode_id: int
) -> AcceptanceReport:
    """Run the real-writing qualification probes against a temporary DB."""
    migration_sequence_ok = _migration_sequence_ok(database)
    tool_inventory_ok = (
        len(TOOL_DESCRIPTIONS) == 23
        and len(PHASE2_TOOL_DESCRIPTIONS) == 27
        and len(PHASE3_TOOL_DESCRIPTIONS) == 5
        and len(
            set(TOOL_DESCRIPTIONS)
            | set(PHASE2_TOOL_DESCRIPTIONS)
            | set(PHASE3_TOOL_DESCRIPTIONS)
        )
        == 55
    )
    draft_append_only, draft_parent_cas_ok, draft_hash_ok = _draft_probes(
        database, episode_id
    )
    try:
        outline = OutlineService(database).get_episode_outline(episode_id)
        outline_payload = json_value(outline)
        outline_safe = _safe_keys(outline_payload) and not _has_deprecated(
            outline_payload
        )
    except Exception:
        outline = None
        outline_payload = {}
        outline_safe = False

    context_read_only = False
    context = None
    context_payload: Any = {}
    try:
        statements: list[str] = []
        database.set_trace_callback(statements.append)
        context = ContextService(database).build_episode_context(episode_id)
        context_payload = json_value(context)
        context_read_only = not any(
            statement.lstrip()
            .upper()
            .startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"))
            for statement in statements
        )
    except Exception:
        context_read_only = False
    finally:
        database.set_trace_callback(None)

    context_bounds_ok = _context_bounds_ok(context)
    future_episode = _future_episode_ok(database, episode_id, context)
    future_state = _future_state_ok(database, episode_id, context)
    future_knowledge = _future_knowledge_ok(database, episode_id, context)
    future_disclosure = _future_disclosure_ok(database, episode_id, context)
    deprecated_ok = context is not None and not _has_deprecated(context_payload)
    other_work_ok = _other_work_ok(database, episode_id)
    private_notes_ok = _keys_absent(outline_payload, {"private_notes", "death_date"})
    profile_json_ok = _keys_absent(
        outline_payload, {"profile_json", "details_json", "notes_json"}
    )
    protected_ok = _protected_statements_absent(database, context_payload, context)
    guard_present = bool(context is not None and context.protected_information_guards)
    ready = all(
        (
            migration_sequence_ok,
            draft_append_only,
            draft_parent_cas_ok,
            draft_hash_ok,
            outline_safe,
            context_read_only,
            context_bounds_ok,
            future_episode,
            future_state,
            future_knowledge,
            future_disclosure,
            deprecated_ok,
            other_work_ok,
            private_notes_ok,
            profile_json_ok,
            protected_ok,
            guard_present,
            tool_inventory_ok,
        )
    )
    return AcceptanceReport(
        migration_sequence_ok=migration_sequence_ok,
        draft_append_only=draft_append_only,
        draft_parent_cas_ok=draft_parent_cas_ok,
        draft_hash_ok=draft_hash_ok,
        outline_safe=outline_safe,
        context_read_only=context_read_only,
        context_bounds_ok=context_bounds_ok,
        future_episode_leakage_blocked=future_episode,
        future_state_leakage_blocked=future_state,
        future_knowledge_leakage_blocked=future_knowledge,
        future_disclosure_leakage_blocked=future_disclosure,
        deprecated_canon_leakage_blocked=deprecated_ok,
        other_work_leakage_blocked=other_work_ok,
        private_notes_leakage_blocked=private_notes_ok,
        profile_json_leakage_blocked=profile_json_ok,
        protected_statement_leakage_blocked=protected_ok,
        guard_present=guard_present,
        tool_inventory_ok=tool_inventory_ok,
        writing_ready=ready,
    )


def _migration_sequence_ok(database: sqlite3.Connection) -> bool:
    try:
        versions = tuple(
            row[0]
            for row in database.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
    except sqlite3.Error:
        return False
    return versions == (
        "001_initial.sql",
        "002_search.sql",
        "003_narrative.sql",
        "004_drafts.sql",
    )


def _draft_probes(
    database: sqlite3.Connection, episode_id: int
) -> tuple[bool, bool, bool]:
    service = DraftService(database)
    try:
        previous = service.get_draft(episode_id)
        first = service.save_draft(
            episode_id,
            "phase3 acceptance draft one",
            None if previous is None else previous.id,
            source_agent="acceptance",
            change_summary="qualification",
        )
        second = service.save_draft(
            episode_id,
            "phase3 acceptance draft two",
            first.id,
        )
        hash_ok = (
            first.content_hash == hashlib.sha256(first.body.encode("utf-8")).hexdigest()
            and second.content_hash
            == hashlib.sha256(second.body.encode("utf-8")).hexdigest()
        )
        try:
            service.save_draft(episode_id, "stale", first.id)
        except VersionConflictError:
            parent_cas_ok = True
        else:
            parent_cas_ok = False
        append_only = _raw_append_only_probe(database, first.id, first.body)
        return append_only, parent_cas_ok, hash_ok
    except Exception:
        return False, False, False


def _raw_append_only_probe(
    database: sqlite3.Connection, draft_id: int, body: str
) -> bool:
    rejected_update = rejected_delete = False
    try:
        database.execute(
            "UPDATE drafts SET body = ? WHERE id = ?", ("changed", draft_id)
        )
    except sqlite3.IntegrityError:
        rejected_update = True
    try:
        database.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    except sqlite3.IntegrityError:
        rejected_delete = True
    stored = database.execute(
        "SELECT body FROM drafts WHERE id = ?", (draft_id,)
    ).fetchone()
    return rejected_update and rejected_delete and stored == (body,)


def _context_bounds_ok(context: Any) -> bool:
    if context is None:
        return False
    meta = context.context_meta
    limits = meta.get("limits", {})
    return (
        len(context.recent_context.previous_episode_summaries) <= PREVIOUS_SUMMARIES_MAX
        and len(context.recent_context.previous_draft_tail) <= PREVIOUS_DRAFT_TAIL_CHARS
        and len(context.world_facts) <= WORLD_FACTS_MAX
        and len(context.timeline_events) <= TIMELINE_EVENTS_MAX
        and len(context.reader_context.known_before_episode)
        + len(context.reader_context.reveal_this_episode)
        <= INFORMATION_ITEMS_MAX + len(context.reader_context.reveal_this_episode)
        and limits
        == {
            "previous_episode_summaries": PREVIOUS_SUMMARIES_MAX,
            "previous_draft_tail_chars": PREVIOUS_DRAFT_TAIL_CHARS,
            "world_facts_max": WORLD_FACTS_MAX,
            "timeline_events_max": TIMELINE_EVENTS_MAX,
            "information_items_max": INFORMATION_ITEMS_MAX,
        }
    )


def _future_episode_ok(
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
    return all(
        (item.chapter_position, item.episode_position) < target
        for item in context.recent_context.previous_episode_summaries
    )


def _future_state_ok(
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
    for participant in context.participants:
        state = participant.effective_state
        if state is None:
            continue
        source_order = repository.get_episode_order(work.id, state.source_episode_id)
        if source_order is None or source_order > target:
            return False
    return True


def _future_knowledge_ok(
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
    for participant in context.participants:
        for item in participant.known_information:
            source_order = repository.get_episode_order(work.id, item.source_episode_id)
            if source_order is None or source_order > target:
                return False
    return True


def _future_disclosure_ok(
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
    return all(
        (boundary := repository.get_episode_order(work.id, disclosure.episode_id))
        is not None
        and boundary <= target
        for item in safe_items
        for disclosure in (repository.disclosure(work.id, item.id),)
        if disclosure is not None
    )


def _other_work_ok(database: sqlite3.Connection, episode_id: int) -> bool:
    work = WorkRepository(database).get()
    if work is None:
        return False
    other = database.execute(
        "SELECT id FROM episodes WHERE work_id != ? ORDER BY id LIMIT 1", (work.id,)
    ).fetchone()
    if other is None:
        return True
    try:
        OutlineService(database).get_episode_outline(other[0])
    except WorkScopeError:
        return True
    except Exception:
        return False
    return False


def _protected_statements_absent(
    database: sqlite3.Connection, payload: Any, context: Any
) -> bool:
    if context is None:
        return False
    work = WorkRepository(database).get()
    if work is None:
        return False
    repository = ContextRepository(database)
    statements = {
        item.statement
        for guard in context.protected_information_guards
        if (item := repository.information(work.id, guard.information_item_id))
        is not None
    }
    serialized = repr(payload)
    return bool(statements) and all(
        statement not in serialized for statement in statements
    )


def _safe_keys(value: Any) -> bool:
    return not _keys(value) & {
        "private_notes",
        "profile_json",
        "death_date",
        "details_json",
        "notes_json",
    }


def _keys_absent(value: Any, forbidden: set[str]) -> bool:
    return not _keys(value) & forbidden


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, (list, tuple)):
        return {key for item in value for key in _keys(item)}
    return set()


def _has_deprecated(value: Any) -> bool:
    if hasattr(value, "canon_status") and value.canon_status == "deprecated":
        return True
    if isinstance(value, dict):
        return any(_has_deprecated(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_deprecated(item) for item in value)
    return False
