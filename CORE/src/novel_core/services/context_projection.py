from __future__ import annotations

import json
from typing import Any

from novel_core.errors import ValidationError
from novel_core.models.context import EffectiveRelationship
from novel_core.models.outline import (
    ProtectedInformationGuard,
    RevealBoundary,
    SafeInformationItem,
)
from novel_core.repositories.disclosure_repository import ReaderDisclosureRecord
from novel_core.repositories.information_repository import InformationItemRecord
from novel_core.repositories.relationship_repository import RelationshipRecord
from novel_core.services.outline_service import GENERIC_GUARD


def parse_beliefs(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError("beliefs must be valid JSON", field="beliefs") from exc


def parse_foreshadowing(value: str) -> tuple[object, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "foreshadowing_notes must be valid JSON", field="foreshadowing_notes"
        ) from exc
    if isinstance(parsed, list):
        return tuple(parsed)
    if parsed is None:
        return ()
    return (parsed,)


def safe_information(item: InformationItemRecord) -> SafeInformationItem:
    return SafeInformationItem(
        id=item.id,
        statement=item.statement,
        truth_status=item.truth_status,
        canon_status=item.canon_status,
        importance=item.importance,
    )


def safe_relationship(
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


def guard_for(
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


def build_context_meta(
    *,
    target_order: tuple[int, int],
    previous_summaries_max: int,
    previous_draft_context_visible_chars_max: int,
    world_facts_max: int,
    timeline_events_max: int,
    information_items_max: int,
    world_facts_returned: int,
    world_facts_total: int,
    timeline_events_returned: int,
    timeline_events_total: int,
    information_returned: int,
    information_total: int,
    previous_returned: int,
    previous_total: int,
    previous_draft_context_blocks: int,
    previous_draft_context_visible_chars: int,
    previous_draft_context_truncated: bool,
    guard_count: int,
) -> dict[str, object]:
    return {
        "narrative_position": {
            "chapter_position": target_order[0],
            "episode_position": target_order[1],
        },
        "limits": {
            "previous_episode_summaries": previous_summaries_max,
            "previous_draft_context_visible_chars": (
                previous_draft_context_visible_chars_max
            ),
            "world_facts_max": world_facts_max,
            "timeline_events_max": timeline_events_max,
            "information_items_max": information_items_max,
        },
        "returned_counts": {
            "previous_episode_summaries": previous_returned,
            "previous_draft_context_blocks": previous_draft_context_blocks,
            "previous_draft_context_visible_chars": (
                previous_draft_context_visible_chars
            ),
            "world_facts": world_facts_returned,
            "timeline_events": timeline_events_returned,
            "information_items": information_returned,
            "protected_information_guards": guard_count,
        },
        "omitted_counts": {
            "previous_episode_summaries": max(0, previous_total - previous_returned),
            "world_facts": max(0, world_facts_total - world_facts_returned),
            "timeline_events": max(0, timeline_events_total - timeline_events_returned),
            "information_items": max(0, information_total - information_items_max),
        },
        "truncated": {
            "world_facts": world_facts_total > world_facts_max,
            "timeline_events": timeline_events_total > timeline_events_max,
            "information_items": information_total > information_items_max,
            "previous_draft_context": previous_draft_context_truncated,
        },
    }
