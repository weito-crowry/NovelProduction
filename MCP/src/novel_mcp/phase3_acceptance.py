from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, fields
from typing import Any

from novel_mcp.errors import VersionConflictError
from novel_mcp.phase2_tool_descriptions import PHASE2_TOOL_DESCRIPTIONS
from novel_mcp.phase3_acceptance_probes import (
    evaluate_active_probes,
    has_deprecated,
    safe_keys,
    seed_active_probes,
    strict_safe_disclosures,
)
from novel_mcp.phase3_tool_descriptions import PHASE3_TOOL_DESCRIPTIONS
from novel_mcp.services.context_service import ContextService
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
    """Run active real-writing qualification probes against a temporary DB."""
    migration_sequence_ok = _migration_sequence_ok(database)
    tool_inventory_ok = _tool_inventory_ok()
    scenario = seed_active_probes(database, episode_id=episode_id)
    draft_append_only, draft_parent_cas_ok, draft_hash_ok = _draft_probes(
        database, episode_id
    )

    try:
        outline = OutlineService(database).get_episode_outline(episode_id)
        outline_payload = json_value(outline)
        outline_safe = safe_keys(outline_payload) and not has_deprecated(
            outline_payload
        )
    except Exception:
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

    probes = evaluate_active_probes(
        database,
        episode_id=episode_id,
        context=context,
        context_payload=context_payload,
        outline_payload=outline_payload,
        scenario=scenario,
    )
    ready = all(
        (
            migration_sequence_ok,
            draft_append_only,
            draft_parent_cas_ok,
            draft_hash_ok,
            outline_safe,
            context_read_only,
            probes.context_bounds_ok,
            probes.future_episode_ok,
            probes.future_state_ok,
            probes.future_knowledge_ok,
            probes.future_disclosure_ok,
            probes.deprecated_ok,
            probes.other_work_ok,
            probes.private_notes_ok,
            probes.profile_json_ok,
            probes.protected_statement_ok,
            probes.guard_present,
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
        context_bounds_ok=probes.context_bounds_ok,
        future_episode_leakage_blocked=probes.future_episode_ok,
        future_state_leakage_blocked=probes.future_state_ok,
        future_knowledge_leakage_blocked=probes.future_knowledge_ok,
        future_disclosure_leakage_blocked=probes.future_disclosure_ok,
        deprecated_canon_leakage_blocked=probes.deprecated_ok,
        other_work_leakage_blocked=probes.other_work_ok,
        private_notes_leakage_blocked=probes.private_notes_ok,
        profile_json_leakage_blocked=probes.profile_json_ok,
        protected_statement_leakage_blocked=probes.protected_statement_ok,
        guard_present=probes.guard_present,
        tool_inventory_ok=tool_inventory_ok,
        writing_ready=ready,
    )


def _tool_inventory_ok() -> bool:
    return (
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


def _future_disclosure_ok(
    database: sqlite3.Connection, episode_id: int, context: Any
) -> bool:
    """Compatibility wrapper for strict disclosure regression tests."""
    return strict_safe_disclosures(database, episode_id, context)


def _has_deprecated(value: Any) -> bool:
    """Compatibility wrapper for deprecated-payload regression tests."""
    return has_deprecated(value)
