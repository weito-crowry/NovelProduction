from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from novel_mcp.tool_errors import error_payload, success
from novel_mcp.tool_support import call_service, json_text

Registrar = Callable[..., None]
Limit = Annotated[int, Field(ge=0, le=100)]
OptionalEpisodeId = Annotated[int | None, Field(ge=1)]
CanonStatus = Literal["idea", "draft", "canon", "deprecated"]
EntityType = Literal[
    "world_fact",
    "timeline_event",
    "character",
    "relationship",
    "chapter",
    "episode",
    "scene",
    "information_item",
]
DatePrecision = Literal["unknown", "year", "season", "month", "day"]


class ParticipantInput(BaseModel):
    character_id: Annotated[int, Field(ge=1)]
    role: Annotated[str, Field(min_length=1, max_length=120)]


def register_phase1_tools(services: Any, register: Registrar) -> None:
    async def work_get() -> dict[str, Any]:
        return await call_service(services.work.get)

    async def work_update(
        working_title: str,
        expected_version: int,
        genre: str | None = None,
        premise: str | None = None,
        themes_json: str
        | dict[str, Any]
        | list[Any]
        | int
        | float
        | bool
        | None = None,
        description: str | None = None,
        production_status: Literal[
            "planned", "outlined", "drafting", "revising", "final"
        ]
        | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.work.update,
            working_title,
            expected_version,
            genre=genre,
            premise=premise,
            themes_json=json_text(themes_json),
            description=description,
            production_status=production_status,
        )

    async def world_fact_create(
        statement: Annotated[str, Field(min_length=1)],
        valid_from: str | None = None,
        valid_to: str | None = None,
        topic_key: str | None = None,
        category: Annotated[str, Field(min_length=1)] = "general",
        title: str | None = None,
        details_json: str = "{}",
        importance: Annotated[int, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        return await call_service(
            services.world.create,
            statement,
            valid_from,
            valid_to,
            topic_key=topic_key,
            category=category,
            title=title,
            details_json=details_json,
            importance=importance,
        )

    async def world_fact_update(
        fact_id: int,
        statement: Annotated[str, Field(min_length=1)],
        expected_version: int,
        reason: str | None = None,
        topic_key: str | None = None,
        category: str | None = None,
        title: str | None = None,
        details_json: str | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        importance: Annotated[int | None, Field(ge=0)] = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.world.update,
            fact_id,
            statement,
            expected_version,
            reason,
            topic_key=topic_key,
            category=category,
            title=title,
            details_json=details_json,
            valid_from=valid_from,
            valid_to=valid_to,
            importance=importance,
        )

    async def world_fact_get(fact_id: int) -> dict[str, Any]:
        return await call_service(services.world.get, fact_id)

    async def world_fact_search(query: str, limit: Limit = 20) -> dict[str, Any]:
        return await call_service(services.search.search_world_facts, query, limit)

    async def timeline_event_create(
        title: Annotated[str, Field(min_length=1)],
        event_date: str | None = None,
        participants: list[ParticipantInput] | None = None,
        event_key: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        date_precision: DatePrecision | None = None,
        date_display: str | None = None,
        description: str = "",
        category: str = "general",
        location_world_fact_id: int | None = None,
        cause_summary: str = "",
        consequence_summary: str = "",
        importance: Annotated[int, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        return await _call(
            services.timeline.create_event,
            event_date,
            title,
            participants=_participants(participants),
            event_key=event_key,
            time_start=time_start,
            time_end=time_end,
            date_precision=date_precision,
            date_display=date_display,
            description=description,
            category=category,
            location_world_fact_id=location_world_fact_id,
            cause_summary=cause_summary,
            consequence_summary=consequence_summary,
            importance=importance,
        )

    async def timeline_event_update(
        event_id: int,
        expected_version: int,
        title: str | None = None,
        new_date: str | None = None,
        participants: list[ParticipantInput] | None = None,
        reason: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        date_precision: DatePrecision | None = None,
        date_display: str | None = None,
        description: str | None = None,
        category: str | None = None,
        location_world_fact_id: int | None = None,
        cause_summary: str | None = None,
        consequence_summary: str | None = None,
        importance: Annotated[int | None, Field(ge=0)] = None,
    ) -> dict[str, Any]:
        return await _call(
            services.timeline.update_event,
            event_id,
            expected_version,
            title=title,
            new_date=new_date,
            participants=_participants(participants),
            reason=reason,
            time_start=time_start,
            time_end=time_end,
            date_precision=date_precision,
            date_display=date_display,
            description=description,
            category=category,
            location_world_fact_id=location_world_fact_id,
            cause_summary=cause_summary,
            consequence_summary=consequence_summary,
            importance=importance,
        )

    async def timeline_event_get(event_id: int) -> dict[str, Any]:
        return await _call(services.timeline.get_event, event_id)

    async def timeline_event_search(query: str, limit: Limit = 20) -> dict[str, Any]:
        return await _call(services.timeline.search_events, query, limit)

    async def timeline_range(start: str, end: str, limit: Limit = 20) -> dict[str, Any]:
        return await _call(services.timeline.range_events, start, end, limit)

    async def timeline_move(
        event_id: int, expected_version: int, new_date: str, reason: str | None = None
    ) -> dict[str, Any]:
        return await _call(
            services.timeline.move_event, event_id, expected_version, new_date, reason
        )

    async def timeline_relation_create(
        source_id: int,
        target_id: int,
        relation_type: Annotated[str, Field(min_length=1)],
    ) -> dict[str, Any]:
        return await _call(
            services.timeline.create_relation, source_id, target_id, relation_type
        )

    async def character_create(
        display_name: Annotated[str, Field(min_length=1)],
        character_key: str | None = None,
        entity_type: Literal["human", "ai", "organization"] = "human",
        description: str = "",
        birth_date: str | None = None,
        death_date: str | None = None,
        physical_description: str = "",
        occupation: str = "",
        core_beliefs: str = "",
        goals: str = "",
        fears: str = "",
        personality: str = "",
        speech_style: str = "",
        ai_attitude: str = "",
        genetic_modification_attitude: str = "",
        private_notes: str = "",
        profile_json: str = "{}",
    ) -> dict[str, Any]:
        return await _call(
            services.character.create,
            display_name=display_name,
            character_key=character_key,
            entity_type=entity_type,
            description=description,
            birth_date=birth_date,
            death_date=death_date,
            physical_description=physical_description,
            occupation=occupation,
            core_beliefs=core_beliefs,
            goals=goals,
            fears=fears,
            personality=personality,
            speech_style=speech_style,
            ai_attitude=ai_attitude,
            genetic_modification_attitude=genetic_modification_attitude,
            private_notes=private_notes,
            profile_json=profile_json,
        )

    async def character_update(
        character_id: int,
        expected_version: int,
        display_name: str | None = None,
        description: str | None = None,
        reason: str | None = None,
        character_key: str | None = None,
        entity_type: Literal["human", "ai", "organization"] | None = None,
        birth_date: str | None = None,
        death_date: str | None = None,
        physical_description: str | None = None,
        occupation: str | None = None,
        core_beliefs: str | None = None,
        goals: str | None = None,
        fears: str | None = None,
        personality: str | None = None,
        speech_style: str | None = None,
        ai_attitude: str | None = None,
        genetic_modification_attitude: str | None = None,
        private_notes: str | None = None,
        profile_json: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            services.character.update,
            character_id,
            expected_version,
            display_name=display_name,
            description=description,
            reason=reason,
            character_key=character_key,
            entity_type=entity_type,
            birth_date=birth_date,
            death_date=death_date,
            physical_description=physical_description,
            occupation=occupation,
            core_beliefs=core_beliefs,
            goals=goals,
            fears=fears,
            personality=personality,
            speech_style=speech_style,
            ai_attitude=ai_attitude,
            genetic_modification_attitude=genetic_modification_attitude,
            private_notes=private_notes,
            profile_json=profile_json,
        )

    async def character_get(character_id: int) -> dict[str, Any]:
        return await _call(services.character.get, character_id)

    async def character_search(query: str, limit: Limit = 20) -> dict[str, Any]:
        return await _call(services.search.search_characters, query, limit)

    async def relationship_create(
        source_character_id: int,
        target_character_id: int,
        relationship_type: Annotated[str, Field(min_length=1)],
        description: str = "",
        valid_from_episode_id: OptionalEpisodeId = None,
        valid_to_episode_id: OptionalEpisodeId = None,
    ) -> dict[str, Any]:
        return await _call(
            services.relationship.create,
            source_character_id,
            target_character_id,
            relationship_type,
            description,
            valid_from_episode_id=valid_from_episode_id,
            valid_to_episode_id=valid_to_episode_id,
        )

    async def relationship_update(
        relationship_id: int,
        expected_version: int,
        relationship_type: Annotated[str, Field(min_length=1)],
        description: str | None = None,
        reason: str | None = None,
        valid_from_episode_id: OptionalEpisodeId = None,
        valid_to_episode_id: OptionalEpisodeId = None,
        clear_valid_from: bool = False,
        clear_valid_to: bool = False,
    ) -> dict[str, Any]:
        return await _call(
            services.relationship.update,
            relationship_id,
            expected_version,
            relationship_type,
            reason,
            description=description,
            valid_from_episode_id=valid_from_episode_id,
            valid_to_episode_id=valid_to_episode_id,
            clear_valid_from=clear_valid_from,
            clear_valid_to=clear_valid_to,
        )

    async def relationship_search(
        character_id: int | None = None, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(services.relationship.search, character_id, limit)

    async def canon_status_set(
        entity_type: EntityType,
        entity_id: int,
        target_status: CanonStatus,
        expected_version: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            services.canon.set_canon_status,
            entity_type,
            entity_id,
            target_status,
            expected_version,
            reason,
        )

    async def canon_decision_get(decision_id: int) -> dict[str, Any]:
        return await _call(services.canon.get_decision, decision_id)

    async def canon_decision_search(query: str, limit: Limit = 20) -> dict[str, Any]:
        return await _call(services.canon.search_decisions, query, limit)

    registrations = (
        ("work_get", work_get, True, False),
        ("work_update", work_update, False, True),
        ("world_fact_create", world_fact_create, False, False),
        ("world_fact_update", world_fact_update, False, True),
        ("world_fact_get", world_fact_get, True, False),
        ("world_fact_search", world_fact_search, True, False),
        ("timeline_event_create", timeline_event_create, False, False),
        ("timeline_event_update", timeline_event_update, False, True),
        ("timeline_event_get", timeline_event_get, True, False),
        ("timeline_event_search", timeline_event_search, True, False),
        ("timeline_range", timeline_range, True, False),
        ("timeline_move", timeline_move, False, True),
        ("timeline_relation_create", timeline_relation_create, False, False),
        ("character_create", character_create, False, False),
        ("character_update", character_update, False, True),
        ("character_get", character_get, True, False),
        ("character_search", character_search, True, False),
        ("relationship_create", relationship_create, False, False),
        ("relationship_update", relationship_update, False, True),
        ("relationship_search", relationship_search, True, False),
        ("canon_status_set", canon_status_set, False, True),
        ("canon_decision_get", canon_decision_get, True, False),
        ("canon_decision_search", canon_decision_search, True, False),
    )
    for name, handler, read_only, destructive in registrations:
        register(name, handler, read_only=read_only, destructive=destructive)


def _participants(
    items: list[ParticipantInput] | None,
) -> tuple[tuple[int, str], ...] | None:
    if items is None:
        return None
    return tuple((item.character_id, item.role) for item in items)


async def _call(
    operation: Callable[..., Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    try:
        return success(operation(*args, **kwargs))
    except Exception as exc:
        return error_payload(exc)


def _json_text(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
