from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any

from pydantic import Field

from novel_mcp.api_client import ApiClient
from novel_mcp.tool_support import call_api
from novel_mcp.tool_types import ProjectId

Registrar = Callable[..., None]
Id = Annotated[int, Field(ge=1)]
OptionalId = Annotated[int | None, Field(ge=1)]
OptionalRevision = Annotated[int | None, Field(ge=1)]
HistoryLimit = Annotated[int, Field(ge=1, le=100)]
SourceAgent = Annotated[str | None, Field(min_length=1, max_length=120)]
ChangeSummary = Annotated[str, Field(max_length=1000)]


def register_phase3_tools(client: ApiClient, register: Registrar) -> None:
    async def episode_outline_get(
        project_id: ProjectId, episode_id: Id
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}/outline"),
            project_id=project_id,
        )

    async def episode_context(project_id: ProjectId, episode_id: Id) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}/context"),
            project_id=project_id,
        )

    async def episode_draft_get(
        project_id: ProjectId, episode_id: Id, revision: OptionalRevision = None
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}/draft"),
            project_id=project_id,
            params=_compact(revision=revision),
        )

    async def episode_draft_save(
        project_id: ProjectId,
        episode_id: Id,
        body: Annotated[str, Field(min_length=1)],
        expected_parent_draft_id: OptionalId = None,
        source_agent: SourceAgent = None,
        change_summary: ChangeSummary = "",
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"episodes/{episode_id}/drafts"),
            project_id=project_id,
            body=_compact(
                body=body,
                expected_parent_draft_id=expected_parent_draft_id,
                source_agent=source_agent,
                change_summary=change_summary,
            ),
        )

    async def episode_draft_history(
        project_id: ProjectId, episode_id: Id, limit: HistoryLimit = 20
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}/drafts"),
            project_id=project_id,
            params={"limit": limit},
        )

    registrations = (
        ("episode_outline_get", episode_outline_get, True, False),
        ("episode_context", episode_context, True, False),
        ("episode_draft_get", episode_draft_get, True, False),
        ("episode_draft_save", episode_draft_save, False, False),
        ("episode_draft_history", episode_draft_history, True, False),
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
