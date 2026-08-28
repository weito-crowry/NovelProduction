from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from novel_mcp.api_client import ApiClient
from novel_mcp.tool_errors import validation_failure
from novel_mcp.tool_support import call_api
from novel_mcp.tool_types import ProjectId

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


def register_phase1_tools(client: ApiClient, register: Registrar) -> None:
    async def work_get(project_id: ProjectId) -> dict[str, Any]:
        return await _call(
            client, "GET", _path(project_id, "work"), project_id=project_id
        )

    async def work_update(
        project_id: ProjectId,
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
        try:
            body = _compact(
                working_title=working_title,
                expected_version=expected_version,
                genre=genre,
                premise=premise,
                themes_json=_json_value(themes_json),
                description=description,
                production_status=production_status,
            )
        except ValueError:
            return validation_failure(
                project_id, "themes_json must contain valid JSON."
            )
        return await _call(
            client, "PATCH", _path(project_id, "work"), project_id=project_id, body=body
        )

    async def world_fact_create(
        project_id: ProjectId,
        statement: Annotated[str, Field(min_length=1)],
        valid_from: str | None = None,
        valid_to: str | None = None,
        topic_key: str | None = None,
        category: Annotated[str, Field(min_length=1)] = "general",
        title: str | None = None,
        details_json: str = "{}",
        importance: Annotated[int, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        try:
            body = _compact(
                statement=statement,
                valid_from=valid_from,
                valid_to=valid_to,
                topic_key=topic_key,
                category=category,
                title=title,
                details_json=_json_value(details_json),
                importance=importance,
            )
        except ValueError:
            return validation_failure(
                project_id, "details_json must contain valid JSON."
            )
        return await _call(
            client,
            "POST",
            _path(project_id, "world-facts"),
            project_id=project_id,
            body=body,
        )

    async def world_fact_update(
        project_id: ProjectId,
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
        try:
            body = _compact(
                statement=statement,
                expected_version=expected_version,
                reason=reason,
                topic_key=topic_key,
                category=category,
                title=title,
                details_json=_json_value(details_json),
                valid_from=valid_from,
                valid_to=valid_to,
                importance=importance,
            )
        except ValueError:
            return validation_failure(
                project_id, "details_json must contain valid JSON."
            )
        return await _call(
            client,
            "PATCH",
            _path(project_id, f"world-facts/{fact_id}"),
            project_id=project_id,
            body=body,
        )

    async def world_fact_get(project_id: ProjectId, fact_id: int) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"world-facts/{fact_id}"),
            project_id=project_id,
        )

    async def world_fact_search(
        project_id: ProjectId, query: str, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, "world-facts/search"),
            project_id=project_id,
            params={"query": query, "limit": limit},
        )

    async def timeline_event_create(
        project_id: ProjectId,
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
        body = _compact(
            title=title,
            event_date=event_date,
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
        return await _call(
            client,
            "POST",
            _path(project_id, "timeline/events"),
            project_id=project_id,
            body=body,
        )

    async def timeline_event_update(
        project_id: ProjectId,
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
        body = _compact(
            expected_version=expected_version,
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
        return await _call(
            client,
            "PATCH",
            _path(project_id, f"timeline/events/{event_id}"),
            project_id=project_id,
            body=body,
        )

    async def timeline_event_get(
        project_id: ProjectId, event_id: int
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"timeline/events/{event_id}"),
            project_id=project_id,
        )

    async def timeline_event_search(
        project_id: ProjectId, query: str, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, "timeline/events/search"),
            project_id=project_id,
            params={"query": query, "limit": limit},
        )

    async def timeline_range(
        project_id: ProjectId, start: str, end: str, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, "timeline/range"),
            project_id=project_id,
            params={"start": start, "end": end, "limit": limit},
        )

    async def timeline_move(
        project_id: ProjectId,
        event_id: int,
        expected_version: int,
        new_date: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"timeline/events/{event_id}/move"),
            project_id=project_id,
            body=_compact(
                expected_version=expected_version, new_date=new_date, reason=reason
            ),
        )

    async def timeline_relation_create(
        project_id: ProjectId,
        source_id: int,
        target_id: int,
        relation_type: Annotated[str, Field(min_length=1)],
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, "timeline/relations"),
            project_id=project_id,
            body={
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
            },
        )

    async def character_create(
        project_id: ProjectId,
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
        try:
            body = _compact(
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
                profile_json=_json_value(profile_json),
            )
        except ValueError:
            return validation_failure(
                project_id, "profile_json must contain valid JSON."
            )
        return await _call(
            client,
            "POST",
            _path(project_id, "characters"),
            project_id=project_id,
            body=body,
        )

    async def character_update(
        project_id: ProjectId,
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
        try:
            body = _compact(
                expected_version=expected_version,
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
                profile_json=_json_value(profile_json),
            )
        except ValueError:
            return validation_failure(
                project_id, "profile_json must contain valid JSON."
            )
        return await _call(
            client,
            "PATCH",
            _path(project_id, f"characters/{character_id}"),
            project_id=project_id,
            body=body,
        )

    async def character_get(project_id: ProjectId, character_id: int) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"characters/{character_id}"),
            project_id=project_id,
        )

    async def character_search(
        project_id: ProjectId, query: str, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, "characters/search"),
            project_id=project_id,
            params={"query": query, "limit": limit},
        )

    async def relationship_create(
        project_id: ProjectId,
        source_character_id: int,
        target_character_id: int,
        relationship_type: Annotated[str, Field(min_length=1)],
        description: str = "",
        valid_from_episode_id: OptionalEpisodeId = None,
        valid_to_episode_id: OptionalEpisodeId = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, "relationships"),
            project_id=project_id,
            body=_compact(
                source_character_id=source_character_id,
                target_character_id=target_character_id,
                relationship_type=relationship_type,
                description=description,
                valid_from_episode_id=valid_from_episode_id,
                valid_to_episode_id=valid_to_episode_id,
            ),
        )

    async def relationship_update(
        project_id: ProjectId,
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
            client,
            "PATCH",
            _path(project_id, f"relationships/{relationship_id}"),
            project_id=project_id,
            body=_compact(
                expected_version=expected_version,
                relationship_type=relationship_type,
                description=description,
                reason=reason,
                valid_from_episode_id=valid_from_episode_id,
                valid_to_episode_id=valid_to_episode_id,
                clear_valid_from=clear_valid_from,
                clear_valid_to=clear_valid_to,
            ),
        )

    async def relationship_search(
        project_id: ProjectId, character_id: int | None = None, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, "relationships"),
            project_id=project_id,
            params=_compact(character_id=character_id, limit=limit),
        )

    async def canon_status_set(
        project_id: ProjectId,
        entity_type: EntityType,
        entity_id: int,
        target_status: CanonStatus,
        expected_version: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, "canon/status"),
            project_id=project_id,
            body=_compact(
                entity_type=entity_type,
                entity_id=entity_id,
                target_status=target_status,
                expected_version=expected_version,
                reason=reason,
            ),
        )

    async def canon_decision_get(
        project_id: ProjectId, decision_id: int
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"canon/decisions/{decision_id}"),
            project_id=project_id,
        )

    async def canon_decision_search(
        project_id: ProjectId, query: str, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, "canon/decisions/search"),
            project_id=project_id,
            params={"query": query, "limit": limit},
        )

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


async def _call(
    client: ApiClient,
    method: str,
    path: str,
    *,
    project_id: str,
    params: Mapping[str, Any] | None = None,
    body: Any = None,
) -> dict[str, Any]:
    return await call_api(
        client, method, path, project_id=project_id, params=params, json_body=body
    )


def _path(project_id: str, suffix: str) -> str:
    return f"/api/v1/projects/{project_id}/{suffix}"


def _compact(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _participants(items: list[ParticipantInput] | None) -> list[dict[str, Any]] | None:
    if items is None:
        return None
    return [{"character_id": item.character_id, "role": item.role} for item in items]


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError from exc
