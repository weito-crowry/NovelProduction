from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from novel_mcp.api_client import ApiClient, project_failure, project_success
from novel_mcp.tool_errors import error_payload, success

Handler = Callable[..., Awaitable[dict[str, Any]]]


async def call_service(
    operation: Callable[..., Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    try:
        return success(operation(*args, **kwargs))
    except Exception as exc:
        return error_payload(exc)


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


def json_value(value: object) -> Any:
    return value


def json_text(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
