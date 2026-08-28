from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from novel_mcp.api_client import ApiClient
from novel_mcp.tool_errors import validation_failure
from novel_mcp.tool_support import call_api
from novel_mcp.tool_types import ProjectId

Registrar = Callable[..., None]
Limit = Annotated[int, Field(ge=0, le=100)]
Version = Annotated[int, Field(ge=1)]
OptionalVersion = Annotated[int | None, Field(ge=1)]
Position = Annotated[int, Field(ge=1)]
Id = Annotated[int, Field(ge=1)]
CanonStatus = Literal["idea", "draft", "canon", "deprecated"]
ProductionStatus = Literal["planned", "outlined", "drafting", "revising", "final"]
TruthStatus = Literal["true", "false", "uncertain", "subjective"]
KnowledgeState = Literal[
    "suspects", "believes", "knows", "confirmed", "doubts", "rejected"
]
ReferenceType = Literal["character", "world_fact", "timeline_event", "information"]


def register_phase2_tools(client: ApiClient, register: Registrar) -> None:
    async def chapter_create(
        project_id: ProjectId,
        title: Annotated[str, Field(min_length=1)],
        summary: str = "",
        purpose: str = "",
        production_status: ProductionStatus = "planned",
        canon_status: CanonStatus = "draft",
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, "chapters"),
            project_id=project_id,
            body=_compact(
                title=title,
                summary=summary,
                purpose=purpose,
                production_status=production_status,
                canon_status=canon_status,
            ),
        )

    async def chapter_update(
        project_id: ProjectId,
        chapter_id: Id,
        expected_version: Version,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        production_status: ProductionStatus | None = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "PATCH",
            _path(project_id, f"chapters/{chapter_id}"),
            project_id=project_id,
            body=_compact(
                expected_version=expected_version,
                title=title,
                summary=summary,
                purpose=purpose,
                production_status=production_status,
                canon_status=canon_status,
                reason=reason,
            ),
        )

    async def chapter_reorder(
        project_id: ProjectId,
        chapter_id: Id,
        target_position: Position,
        expected_version: Version,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"chapters/{chapter_id}/reorder"),
            project_id=project_id,
            body={
                "target_position": target_position,
                "expected_version": expected_version,
            },
        )

    async def chapter_list(project_id: ProjectId) -> dict[str, Any]:
        return await _call(
            client, "GET", _path(project_id, "chapters"), project_id=project_id
        )

    async def episode_create(
        project_id: ProjectId,
        chapter_id: Id,
        title: Annotated[str, Field(min_length=1)],
        summary: str = "",
        purpose: str = "",
        foreshadowing_notes: Any = None,
        production_status: ProductionStatus = "planned",
        canon_status: CanonStatus = "draft",
    ) -> dict[str, Any]:
        return await _call_json(
            client,
            "POST",
            _path(project_id, f"chapters/{chapter_id}/episodes"),
            project_id=project_id,
            body=_compact(
                title=title,
                summary=summary,
                purpose=purpose,
                foreshadowing_notes=foreshadowing_notes,
                production_status=production_status,
                canon_status=canon_status,
            ),
            json_fields=("foreshadowing_notes",),
        )

    async def episode_update(
        project_id: ProjectId,
        episode_id: Id,
        expected_version: Version,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        foreshadowing_notes: Any = None,
        production_status: ProductionStatus | None = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await _call_json(
            client,
            "PATCH",
            _path(project_id, f"episodes/{episode_id}"),
            project_id=project_id,
            body=_compact(
                expected_version=expected_version,
                title=title,
                summary=summary,
                purpose=purpose,
                foreshadowing_notes=foreshadowing_notes,
                production_status=production_status,
                canon_status=canon_status,
                reason=reason,
            ),
            json_fields=("foreshadowing_notes",),
        )

    async def episode_get(project_id: ProjectId, episode_id: Id) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}"),
            project_id=project_id,
        )

    async def episode_reorder(
        project_id: ProjectId,
        episode_id: Id,
        target_position: Position,
        expected_version: Version,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"episodes/{episode_id}/reorder"),
            project_id=project_id,
            body={
                "target_position": target_position,
                "expected_version": expected_version,
            },
        )

    async def episode_list(project_id: ProjectId, chapter_id: Id) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"chapters/{chapter_id}/episodes"),
            project_id=project_id,
        )

    async def scene_create(
        project_id: ProjectId,
        episode_id: Id,
        title: Annotated[str, Field(min_length=1)],
        summary: str = "",
        purpose: str = "",
        production_status: ProductionStatus = "planned",
        canon_status: CanonStatus = "draft",
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"episodes/{episode_id}/scenes"),
            project_id=project_id,
            body=_compact(
                title=title,
                summary=summary,
                purpose=purpose,
                production_status=production_status,
                canon_status=canon_status,
            ),
        )

    async def scene_update(
        project_id: ProjectId,
        scene_id: Id,
        expected_version: Version,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        production_status: ProductionStatus | None = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "PATCH",
            _path(project_id, f"scenes/{scene_id}"),
            project_id=project_id,
            body=_compact(
                expected_version=expected_version,
                title=title,
                summary=summary,
                purpose=purpose,
                production_status=production_status,
                canon_status=canon_status,
                reason=reason,
            ),
        )

    async def scene_get(project_id: ProjectId, scene_id: Id) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"scenes/{scene_id}"),
            project_id=project_id,
        )

    async def scene_reorder(
        project_id: ProjectId,
        scene_id: Id,
        target_position: Position,
        expected_version: Version,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"scenes/{scene_id}/reorder"),
            project_id=project_id,
            body={
                "target_position": target_position,
                "expected_version": expected_version,
            },
        )

    async def scene_list(project_id: ProjectId, episode_id: Id) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}/scenes"),
            project_id=project_id,
        )

    async def episode_reference_add(
        project_id: ProjectId,
        episode_id: Id,
        reference_type: ReferenceType,
        target_id: Id,
        role: Annotated[str, Field(min_length=1, max_length=120)] = "participant",
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"episodes/{episode_id}/references"),
            project_id=project_id,
            body={
                "reference_type": reference_type,
                "target_id": target_id,
                "role": role,
            },
        )

    async def episode_reference_remove(
        project_id: ProjectId,
        episode_id: Id,
        reference_type: ReferenceType,
        target_id: Id,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "DELETE",
            _path(
                project_id,
                f"episodes/{episode_id}/references/{reference_type}/{target_id}",
            ),
            project_id=project_id,
        )

    async def episode_reference_list(
        project_id: ProjectId,
        episode_id: Id,
        reference_type: ReferenceType | None = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}/references"),
            project_id=project_id,
            params=_compact(reference_type=reference_type),
        )

    async def character_state_set(
        project_id: ProjectId,
        character_id: Id,
        episode_id: Id,
        physical_state: str | None = None,
        emotional_state: str | None = None,
        beliefs_json: Any = None,
        location_world_fact_id: Id | None = None,
        state_json: Any = None,
        expected_version: OptionalVersion = None,
    ) -> dict[str, Any]:
        return await _call_json(
            client,
            "PUT",
            _path(project_id, f"characters/{character_id}/states/{episode_id}"),
            project_id=project_id,
            body=_compact(
                physical_state=physical_state,
                emotional_state=emotional_state,
                beliefs_json=beliefs_json,
                location_world_fact_id=location_world_fact_id,
                state_json=state_json,
                expected_version=expected_version,
            ),
            json_fields=("beliefs_json", "state_json"),
        )

    async def character_state_get(
        project_id: ProjectId, character_id: Id, episode_id: Id
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"characters/{character_id}/states/{episode_id}"),
            project_id=project_id,
        )

    async def character_state_history(
        project_id: ProjectId, character_id: Id
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"characters/{character_id}/states"),
            project_id=project_id,
        )

    async def information_create(
        project_id: ProjectId,
        statement: Annotated[str, Field(min_length=1)],
        truth_status: TruthStatus = "uncertain",
        authoring_guard: str = "",
        notes_json: Any = None,
        canon_status: CanonStatus = "draft",
        importance: Annotated[int, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        return await _call_json(
            client,
            "POST",
            _path(project_id, "information"),
            project_id=project_id,
            body=_compact(
                statement=statement,
                truth_status=truth_status,
                authoring_guard=authoring_guard,
                notes_json=notes_json,
                canon_status=canon_status,
                importance=importance,
            ),
            json_fields=("notes_json",),
        )

    async def information_update(
        project_id: ProjectId,
        information_item_id: Id,
        expected_version: Version,
        statement: str | None = None,
        truth_status: TruthStatus | None = None,
        authoring_guard: str | None = None,
        notes_json: Any = None,
        importance: Annotated[int | None, Field(ge=0)] = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await _call_json(
            client,
            "PATCH",
            _path(project_id, f"information/{information_item_id}"),
            project_id=project_id,
            body=_compact(
                expected_version=expected_version,
                statement=statement,
                truth_status=truth_status,
                authoring_guard=authoring_guard,
                notes_json=notes_json,
                importance=importance,
                canon_status=canon_status,
                reason=reason,
            ),
            json_fields=("notes_json",),
        )

    async def information_get(
        project_id: ProjectId, information_item_id: Id
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"information/{information_item_id}"),
            project_id=project_id,
        )

    async def information_search(
        project_id: ProjectId, query: str, limit: Limit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, "information/search"),
            project_id=project_id,
            params={"query": query, "limit": limit},
        )

    async def reader_disclosure_set(
        project_id: ProjectId,
        information_item_id: Id,
        episode_id: Id,
        expected_version: OptionalVersion = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "PUT",
            _path(project_id, f"information/{information_item_id}/reader-disclosure"),
            project_id=project_id,
            body=_compact(episode_id=episode_id, expected_version=expected_version),
        )

    async def character_knowledge_set(
        project_id: ProjectId,
        character_id: Id,
        information_item_id: Id,
        episode_id: Id,
        knowledge_state: KnowledgeState,
        note: str = "",
        expected_version: OptionalVersion = None,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "PUT",
            _path(
                project_id, f"characters/{character_id}/knowledge/{information_item_id}"
            ),
            project_id=project_id,
            body=_compact(
                episode_id=episode_id,
                knowledge_state=knowledge_state,
                note=note,
                expected_version=expected_version,
            ),
        )

    async def character_knowledge_get(
        project_id: ProjectId, character_id: Id, episode_id: Id
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"characters/{character_id}/knowledge"),
            project_id=project_id,
            params={"episode_id": episode_id},
        )

    registrations = (
        ("chapter_create", chapter_create, False, False),
        ("chapter_update", chapter_update, False, True),
        ("chapter_reorder", chapter_reorder, False, True),
        ("chapter_list", chapter_list, True, False),
        ("episode_create", episode_create, False, False),
        ("episode_update", episode_update, False, True),
        ("episode_get", episode_get, True, False),
        ("episode_reorder", episode_reorder, False, True),
        ("episode_list", episode_list, True, False),
        ("scene_create", scene_create, False, False),
        ("scene_update", scene_update, False, True),
        ("scene_get", scene_get, True, False),
        ("scene_reorder", scene_reorder, False, True),
        ("scene_list", scene_list, True, False),
        ("episode_reference_add", episode_reference_add, False, False),
        ("episode_reference_remove", episode_reference_remove, False, True),
        ("episode_reference_list", episode_reference_list, True, False),
        ("character_state_set", character_state_set, False, True),
        ("character_state_get", character_state_get, True, False),
        ("character_state_history", character_state_history, True, False),
        ("information_create", information_create, False, False),
        ("information_update", information_update, False, True),
        ("information_get", information_get, True, False),
        ("information_search", information_search, True, False),
        ("reader_disclosure_set", reader_disclosure_set, False, True),
        ("character_knowledge_set", character_knowledge_set, False, True),
        ("character_knowledge_get", character_knowledge_get, True, False),
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


async def _call_json(
    client: ApiClient,
    method: str,
    path: str,
    *,
    project_id: str,
    body: Mapping[str, Any],
    json_fields: Collection[str],
) -> dict[str, Any]:
    normalized = dict(body)
    for field_name in json_fields:
        if field_name in normalized:
            try:
                normalized[field_name] = _json_value(normalized[field_name])
            except (TypeError, ValueError):
                return validation_failure(
                    project_id, f"{field_name} must contain valid JSON."
                )
    return await _call(client, method, path, project_id=project_id, body=normalized)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError from exc
    return value


def _path(project_id: str, suffix: str) -> str:
    return f"/api/v1/projects/{project_id}/{suffix}"


def _compact(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
