from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

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
DraftFormat = Literal["html", "web", "document"]
AnnotationProjection = Literal["none", "selected", "all"]


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
        project_id: ProjectId,
        episode_id: Id,
        revision: OptionalRevision = None,
        format: DraftFormat = "html",
        annotation_projection: AnnotationProjection = "none",
        annotation_keys: list[str] | None = None,
        include_notes: bool = False,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"episodes/{episode_id}/draft"),
            project_id=project_id,
            params=_draft_get_params(
                revision=revision,
                format=format,
                annotation_projection=annotation_projection,
                annotation_keys=annotation_keys,
                include_notes=include_notes,
            ),
        )

    async def episode_draft_save(
        project_id: ProjectId,
        episode_id: Id,
        plain_text: str | None = None,
        html: str | None = None,
        metadata_updates: dict[str, Any] | None = None,
        restore_revision: OptionalRevision = None,
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
                plain_text=plain_text,
                html=html,
                metadata_updates=metadata_updates,
                restore_revision=restore_revision,
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


def _draft_get_params(
    *,
    revision: int | None,
    format: DraftFormat,
    annotation_projection: AnnotationProjection,
    annotation_keys: list[str] | None,
    include_notes: bool,
) -> dict[str, Any]:
    params = _compact(revision=revision)
    if format != "html":
        params["format"] = format
    if annotation_projection != "none":
        params["annotation_projection"] = annotation_projection
    if annotation_keys:
        params["annotation_keys"] = annotation_keys
    if include_notes:
        params["include_notes"] = include_notes
    return params
