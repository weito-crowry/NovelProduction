from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from novel_mcp.api_client import ApiClient
from novel_mcp.tool_errors import validation_failure
from novel_mcp.tool_support import call_api
from novel_mcp.tool_types import ProjectId

Registrar = Callable[..., None]
Id = Annotated[int, Field(ge=1)]
OptionalId = Annotated[int | None, Field(ge=1)]
Limit = Annotated[int, Field(ge=1, le=100)]
Status = Literal["active", "succeeded", "partial", "failed", "cancelled"]
CatalogView = Literal[
    "documents",
    "document",
    "reference_works",
    "reference_work",
    "reference_episodes",
    "reference_episode",
    "external_sessions",
]
ResultView = Literal["semantics", "metrics", "scene_metrics"]


class StyleAnalysisDocumentTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["document"]
    document_id: Annotated[int, Field(ge=1)]
    text_revision_id: Annotated[int, Field(ge=1)]
    structure_revision_id: Annotated[int | None, Field(ge=1)] = None


class StyleAnalysisReferenceWorkTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["reference_work"]
    reference_work_id: Annotated[int, Field(ge=1)]


class StyleAnalysisProjectEpisodeTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["project_episode"]
    episode_id: Annotated[int, Field(ge=1)]
    draft_id: Annotated[int, Field(ge=1)]


StyleAnalysisTarget = Annotated[
    StyleAnalysisDocumentTarget
    | StyleAnalysisReferenceWorkTarget
    | StyleAnalysisProjectEpisodeTarget,
    Field(discriminator="kind"),
]


def register_style_analysis_tools(client: ApiClient, register: Registrar) -> None:
    async def style_analysis_catalog_get(
        project_id: ProjectId,
        view: CatalogView,
        document_id: OptionalId = None,
        reference_work_id: OptionalId = None,
        reference_episode_id: OptionalId = None,
        status: Status | None = None,
        limit: Limit = 20,
    ) -> dict[str, Any]:
        required = {
            "document": document_id,
            "reference_work": reference_work_id,
            "reference_episodes": reference_work_id,
            "reference_episode": reference_episode_id,
        }
        if view in required and required[view] is None:
            return validation_failure(project_id, f"{view} requires its id")
        path, params = _catalog_request(
            project_id,
            view,
            document_id=document_id,
            reference_work_id=reference_work_id,
            reference_episode_id=reference_episode_id,
            status=status,
            limit=limit,
        )
        return await _call(client, "GET", path, project_id=project_id, params=params)

    async def style_analysis_result_get(
        project_id: ProjectId,
        document_id: Id,
        structure_revision_id: Id,
        view: ResultView,
        scene_id: OptionalId = None,
    ) -> dict[str, Any]:
        if view == "scene_metrics" and scene_id is None:
            return validation_failure(project_id, "scene_metrics requires scene_id")
        if view != "scene_metrics" and scene_id is not None:
            return validation_failure(
                project_id, "scene_id is only valid for scene_metrics"
            )
        if view == "semantics":
            suffix = f"documents/{document_id}/semantics"
        elif view == "metrics":
            suffix = f"documents/{document_id}/metrics"
        else:
            suffix = f"documents/{document_id}/scenes/{scene_id}/metrics"
        return await _call(
            client,
            "GET",
            _path(project_id, suffix),
            project_id=project_id,
            params={"structure_revision_id": structure_revision_id},
        )

    async def style_analysis_external_start(
        project_id: ProjectId,
        target: StyleAnalysisTarget,
        executor_model_id: Annotated[str, Field(min_length=1)],
        rebuild_structure: bool = False,
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, "external-sessions"),
            project_id=project_id,
            body={
                "target": target.model_dump()
                if isinstance(target, BaseModel)
                else target,
                "executor_model_id": executor_model_id,
                "rebuild_structure": rebuild_structure,
            },
        )

    async def style_analysis_external_status(
        project_id: ProjectId, session_id: Id
    ) -> dict[str, Any]:
        return await _call(
            client,
            "GET",
            _path(project_id, f"external-sessions/{session_id}"),
            project_id=project_id,
        )

    async def style_analysis_external_submit(
        project_id: ProjectId,
        session_id: Id,
        task_id: Id,
        expected_task_version: Annotated[int, Field(ge=1)],
        executor_model_id: Annotated[str, Field(min_length=1)],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"external-sessions/{session_id}/tasks/{task_id}/submit"),
            project_id=project_id,
            body={
                "expected_task_version": expected_task_version,
                "executor_model_id": executor_model_id,
                "response": response,
            },
        )

    async def style_analysis_external_cancel(
        project_id: ProjectId,
        session_id: Id,
        expected_session_version: Annotated[int, Field(ge=1)],
    ) -> dict[str, Any]:
        return await _call(
            client,
            "POST",
            _path(project_id, f"external-sessions/{session_id}/cancel"),
            project_id=project_id,
            body={"expected_session_version": expected_session_version},
        )

    registrations = (
        ("style_analysis_catalog_get", style_analysis_catalog_get, True, False),
        ("style_analysis_result_get", style_analysis_result_get, True, False),
        (
            "style_analysis_external_start",
            style_analysis_external_start,
            False,
            False,
        ),
        (
            "style_analysis_external_status",
            style_analysis_external_status,
            True,
            False,
        ),
        (
            "style_analysis_external_submit",
            style_analysis_external_submit,
            False,
            False,
        ),
        (
            "style_analysis_external_cancel",
            style_analysis_external_cancel,
            False,
            False,
        ),
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
    return f"/api/v1/projects/{project_id}/style-analysis/{suffix}"


def _catalog_request(
    project_id: str,
    view: CatalogView,
    *,
    document_id: int | None,
    reference_work_id: int | None,
    reference_episode_id: int | None,
    status: Status | None,
    limit: int,
) -> tuple[str, dict[str, Any]]:
    if view == "documents":
        return _path(project_id, "documents"), {}
    if view == "document":
        return _path(project_id, f"documents/{document_id}"), {}
    if view == "reference_works":
        return _path(project_id, "reference-works"), {}
    if view == "reference_work":
        return _path(project_id, f"reference-works/{reference_work_id}"), {}
    if view == "reference_episodes":
        return _path(project_id, f"reference-works/{reference_work_id}/episodes"), {}
    if view == "reference_episode":
        return _path(project_id, f"reference-episodes/{reference_episode_id}"), {}
    params: dict[str, Any] = {"limit": limit}
    if status is not None:
        params["status"] = status
    return _path(project_id, "external-sessions"), params
