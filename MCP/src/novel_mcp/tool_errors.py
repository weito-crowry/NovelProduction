from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from novel_mcp.api_client import (
    BackendUnavailableError,
    RemoteApiError,
    project_failure,
)


def success(value: Any) -> dict[str, Any]:
    return {"ok": True, "data": json_value(value)}


def error_payload(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, (BackendUnavailableError, RemoteApiError)):
        return project_failure(exc)
    return project_failure(exc)


def json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [json_value(item) for item in value]
    return value
