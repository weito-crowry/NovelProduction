from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from novel_mcp.api_client import ApiClient, project_failure, project_success
from novel_mcp.tool_errors import success

Handler = Callable[..., Awaitable[dict[str, Any]]]


async def call_api(
    client: ApiClient,
    method: str,
    path: str,
    *,
    project_id: str | None = None,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
) -> dict[str, Any]:
    try:
        payload = await client.request_json(
            method, path, params=params, json_body=json_body
        )
        if project_id is None:
            return success(payload)
        return project_success(payload, project_id)
    except Exception as exc:
        return project_failure(exc, project_id)
