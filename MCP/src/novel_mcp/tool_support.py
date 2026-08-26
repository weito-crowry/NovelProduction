from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from novel_mcp.tool_errors import error_payload, success

Handler = Callable[..., Awaitable[dict[str, Any]]]


async def call_service(
    operation: Callable[..., Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    try:
        return success(operation(*args, **kwargs))
    except Exception as exc:
        return error_payload(exc)


def json_text(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
