from __future__ import annotations

from typing import Any

from novel_mcp.api_client import (
    BackendUnavailableError,
    RemoteApiError,
    project_failure,
)


def success(value: Any) -> dict[str, Any]:
    return {"ok": True, "data": value}


def validation_failure(
    project_id: str | None, message: str = "The request is invalid."
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": "VALIDATION_ERROR",
            "message": message,
            "project_id": project_id,
            "details": {},
        },
    }


def transport_failure(
    exc: BaseException, project_id: str | None = None
) -> dict[str, Any]:
    if isinstance(exc, (BackendUnavailableError, RemoteApiError)):
        return project_failure(exc, project_id)
    return project_failure(exc, project_id)
