from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from novel_mcp.api_client import ApiClient, BackendProtocolError, project_failure
from novel_mcp.tool_support import call_api
from novel_mcp.tool_types import ProjectId

Registrar = Callable[..., None]
WorkingTitle = Annotated[str, Field(min_length=1)]


def register_project_tools(client: ApiClient, register: Registrar) -> None:
    async def project_list(include_archived: bool = False) -> dict[str, Any]:
        result = await call_api(
            client,
            "GET",
            "/api/v1/projects",
            params={"include_archived": include_archived},
        )
        if not result["ok"]:
            return result
        data = result["data"]
        if not isinstance(data, Mapping) or not isinstance(data.get("projects"), list):
            return project_failure(BackendProtocolError())
        return {"ok": True, "data": {"projects": data["projects"]}}

    async def project_get(project_id: ProjectId) -> dict[str, Any]:
        return await _project_summary(
            client, "GET", f"/api/v1/projects/{project_id}", project_id=project_id
        )

    async def project_create(
        working_title: WorkingTitle, project_id: ProjectId | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"working_title": working_title}
        if project_id is not None:
            body["project_id"] = project_id
        return await _project_summary(
            client, "POST", "/api/v1/projects", json_body=body
        )

    async def project_update(
        project_id: ProjectId, status: Literal["active", "archived"]
    ) -> dict[str, Any]:
        return await _project_summary(
            client,
            "PATCH",
            f"/api/v1/projects/{project_id}",
            project_id=project_id,
            json_body={"status": status},
        )

    registrations = (
        ("project_list", project_list, True, False),
        ("project_get", project_get, True, False),
        ("project_create", project_create, False, False),
        ("project_update", project_update, False, True),
    )
    for name, handler, read_only, destructive in registrations:
        register(name, handler, read_only=read_only, destructive=destructive)


async def _project_summary(
    client: ApiClient,
    method: str,
    path: str,
    *,
    project_id: str | None = None,
    json_body: Any = None,
) -> dict[str, Any]:
    result = await call_api(
        client,
        method,
        path,
        project_id=None,
        json_body=json_body,
    )
    if not result["ok"]:
        return result
    data = result["data"]
    if not isinstance(data, Mapping):
        return project_failure(BackendProtocolError(), project_id)
    response_project_id = data.get("project_id")
    if not isinstance(response_project_id, str):
        return project_failure(BackendProtocolError(), project_id)
    if project_id is not None and response_project_id != project_id:
        return project_failure(BackendProtocolError(), project_id)
    return {
        "ok": True,
        "project_id": response_project_id,
        "data": dict(data),
    }
