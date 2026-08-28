from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from novel_mcp.config import McpSettings


class RemoteApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        project_id: str | None,
        details: dict[str, Any],
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.project_id = project_id
        self.details = details
        super().__init__(message)


class BackendUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("NovelProduction API is unavailable.")


class BackendProtocolError(Exception):
    def __init__(self) -> None:
        super().__init__("NovelProduction API returned an invalid response.")


class ApiClient:
    def __init__(
        self,
        settings: McpSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        timeout = httpx.Timeout(
            settings.request_timeout_seconds,
            connect=settings.connect_timeout_seconds,
            read=settings.request_timeout_seconds,
            write=settings.request_timeout_seconds,
            pool=settings.request_timeout_seconds,
        )
        self._client = httpx.AsyncClient(
            base_url=settings.api_url,
            timeout=timeout,
            transport=transport,
        )

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                json=json_body,
            )
        except httpx.RequestError as exc:
            raise BackendUnavailableError from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendProtocolError from exc

        if not 200 <= response.status_code < 300:
            raise _remote_error(response.status_code, payload)
        return payload

    async def aclose(self) -> None:
        await self._client.aclose()


def project_success(payload: Any, requested_project_id: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise BackendProtocolError
    response_project_id = payload.get("project_id")
    if response_project_id != requested_project_id or "data" not in payload:
        raise BackendProtocolError
    return {
        "ok": True,
        "project_id": requested_project_id,
        "data": payload["data"],
    }


def project_failure(
    exc: BaseException, requested_project_id: str | None = None
) -> dict[str, Any]:
    if isinstance(exc, RemoteApiError):
        project_id = (
            exc.project_id if exc.project_id is not None else requested_project_id
        )
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "project_id": project_id,
                "details": exc.details,
            },
        }
    if isinstance(exc, BackendUnavailableError):
        return {
            "ok": False,
            "error": {
                "code": "BACKEND_UNAVAILABLE",
                "message": "NovelProduction API is unavailable.",
                "project_id": requested_project_id,
                "details": {},
            },
        }
    return {
        "ok": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal server error occurred.",
            "project_id": requested_project_id,
            "details": {},
        },
    }


def _remote_error(status_code: int, payload: Any) -> RemoteApiError:
    if not isinstance(payload, Mapping):
        raise BackendProtocolError
    error = payload.get("error")
    if not isinstance(error, Mapping):
        raise BackendProtocolError
    code = error.get("code")
    message = error.get("message")
    project_id = error.get("project_id")
    details = error.get("details")
    if (
        not isinstance(code, str)
        or not isinstance(message, str)
        or (project_id is not None and not isinstance(project_id, str))
        or not isinstance(details, Mapping)
    ):
        raise BackendProtocolError
    return RemoteApiError(
        status_code=status_code,
        code=code,
        message=message,
        project_id=project_id,
        details={str(key): value for key, value in details.items()},
    )
