from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from novel_core.errors import (
    CanonDecisionNotFoundError,
    CanonEntityNotFoundError,
    CanonPolicyError,
    CanonReasonRequired,
    CharacterNotFoundError,
    DeprecatedCanonForbiddenError,
    NarrativeNotFoundError,
    NovelMcpError,
    OrderConflictError,
    RelationshipIntegrityError,
    RelationshipNotFoundError,
    TimelineEventNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
    WorkScopeError,
    WorldFactNotFoundError,
)
from starlette.exceptions import HTTPException

from novel_api.project_registry import ProjectConflictError, ProjectNotFoundError
from novel_api.schemas.common import ApiError, ErrorEnvelope
from novel_api.serialization import serialize_value

_MISSING = object()
_CORE_NOT_FOUND_ERRORS = (
    WorkNotFoundError,
    WorldFactNotFoundError,
    TimelineEventNotFoundError,
    CharacterNotFoundError,
    RelationshipNotFoundError,
    NarrativeNotFoundError,
    CanonDecisionNotFoundError,
    CanonEntityNotFoundError,
)


@dataclass(frozen=True, slots=True)
class _ErrorSpec:
    status_code: int
    code: str
    message: str


_VALIDATION = _ErrorSpec(400, "VALIDATION_ERROR", "The request is invalid.")
_PROJECT_NOT_FOUND = _ErrorSpec(
    404, "PROJECT_NOT_FOUND", "The requested project was not found."
)
_NOT_FOUND = _ErrorSpec(404, "NOT_FOUND", "The requested resource was not found.")
_PROJECT_CONFLICT = _ErrorSpec(
    409, "PROJECT_CONFLICT", "The requested project already exists."
)
_VERSION_CONFLICT = _ErrorSpec(
    409,
    "VERSION_CONFLICT",
    "The resource was modified by another client.",
)
_ORDER_CONFLICT = _ErrorSpec(
    409,
    "ORDER_CONFLICT",
    "The requested order conflicts with the current resource order.",
)
_DEPENDENCY_CONFLICT = _ErrorSpec(
    409,
    "DEPENDENCY_CONFLICT",
    "The request conflicts with related resources.",
)
_DATABASE_BUSY = _ErrorSpec(503, "DATABASE_BUSY", "The database is temporarily busy.")
_INTERNAL_ERROR = _ErrorSpec(
    500, "INTERNAL_ERROR", "An internal server error occurred."
)


class ApiVersionConflictError(VersionConflictError):
    code = "VersionConflictError"

    def __init__(self, details: dict[str, Any]) -> None:
        self.details = details
        super().__init__("VERSION_CONFLICT")


def build_conflict_details(
    *,
    entity_type: str,
    entity_id: int | str,
    expected_version: int,
    current_version: int,
    current_resource: Any = _MISSING,
    read_current: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    if current_resource is not _MISSING and read_current is not None:
        raise ValueError("provide current_resource or read_current, not both")
    if read_current is not None:
        current_resource = read_current()

    details: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "expected_version": expected_version,
        "current_version": current_version,
    }
    if current_resource is not _MISSING:
        details["current_resource"] = serialize_value(current_resource)
    return details


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(HTTPException, _handle_http_exception)
    app.add_exception_handler(ProjectNotFoundError, _handle_normalized_exception)
    app.add_exception_handler(ProjectConflictError, _handle_normalized_exception)
    app.add_exception_handler(NovelMcpError, _handle_normalized_exception)
    app.add_exception_handler(ValueError, _handle_normalized_exception)
    app.add_exception_handler(sqlite3.IntegrityError, _handle_normalized_exception)
    app.add_exception_handler(sqlite3.OperationalError, _handle_normalized_exception)
    app.add_exception_handler(Exception, _handle_normalized_exception)


async def _handle_request_validation(request: Request, exc: Exception) -> Response:
    if not _is_api_request(request):
        assert isinstance(exc, RequestValidationError)
        return await request_validation_exception_handler(request, exc)
    return _error_response(
        request,
        _VALIDATION,
        status_code=422 if _is_d3_browse_query_validation(request, exc) else None,
    )


async def _handle_http_exception(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, HTTPException)
    if not _is_api_request(request):
        return await http_exception_handler(request, exc)
    return _error_response(request, _http_error_spec(exc))


async def _handle_normalized_exception(request: Request, exc: Exception) -> Response:
    if not _is_api_request(request):
        return PlainTextResponse("Internal Server Error", status_code=500)
    spec = _error_spec(exc)
    details = _domain_details(exc)
    return _error_response(request, spec, details=details)


def _error_spec(exc: Exception) -> _ErrorSpec:
    if isinstance(exc, ProjectNotFoundError):
        return _PROJECT_NOT_FOUND
    if isinstance(exc, ProjectConflictError):
        return _PROJECT_CONFLICT
    if isinstance(exc, (WorkScopeError, *_CORE_NOT_FOUND_ERRORS)):
        return _NOT_FOUND
    if isinstance(exc, VersionConflictError):
        return _VERSION_CONFLICT
    if isinstance(exc, OrderConflictError):
        return _ORDER_CONFLICT
    if isinstance(
        exc,
        RelationshipIntegrityError
        | CanonPolicyError
        | CanonReasonRequired
        | DeprecatedCanonForbiddenError,
    ):
        return _DEPENDENCY_CONFLICT
    if isinstance(exc, sqlite3.IntegrityError):
        return _DEPENDENCY_CONFLICT
    if isinstance(exc, sqlite3.OperationalError):
        return _DATABASE_BUSY if _is_locked(exc) else _INTERNAL_ERROR
    if isinstance(exc, ValidationError | ValueError):
        return _VALIDATION
    return _INTERNAL_ERROR


def _http_error_spec(exc: HTTPException) -> _ErrorSpec:
    if exc.detail == "PROJECT_NOT_FOUND":
        return _PROJECT_NOT_FOUND
    if exc.detail == "PROJECT_CONFLICT":
        return _PROJECT_CONFLICT
    if exc.status_code in (400, 422):
        return _VALIDATION
    if exc.status_code == 404:
        return _NOT_FOUND
    if exc.status_code == 409:
        return _DEPENDENCY_CONFLICT
    if exc.status_code == 503:
        return _DATABASE_BUSY
    return _ErrorSpec(
        exc.status_code,
        "INTERNAL_ERROR",
        "The request could not be completed.",
    )


def _domain_details(exc: Exception) -> dict[str, Any]:
    if not isinstance(exc, NovelMcpError):
        return {}
    code = getattr(exc, "code", type(exc).__name__)
    domain_code = code if isinstance(code, str) else type(exc).__name__
    if isinstance(exc, ApiVersionConflictError):
        return {**exc.details, "domain_code": domain_code}
    return {"domain_code": domain_code}


def _error_response(
    request: Request,
    spec: _ErrorSpec,
    *,
    details: dict[str, Any] | None = None,
    status_code: int | None = None,
) -> JSONResponse:
    payload = ErrorEnvelope(
        error=ApiError(
            code=spec.code,
            message=spec.message,
            project_id=_project_id(request),
            details={} if details is None else details,
        )
    )
    return JSONResponse(
        status_code=spec.status_code if status_code is None else status_code,
        content=payload.model_dump(),
    )


def _is_d3_browse_query_validation(request: Request, exc: Exception) -> bool:
    if request.url.path.rsplit("/", 1)[-1] not in {
        "world-facts",
        "characters",
        "events",
        "relations",
    }:
        return False
    if not request.url.path.startswith("/api/v1/projects/"):
        return False
    if not isinstance(exc, RequestValidationError):
        return False
    return any(
        len(error.get("loc", ())) >= 2
        and error["loc"][0] == "query"
        and error["loc"][1] in {"limit", "offset", "event_id"}
        for error in exc.errors()
    )


def _project_id(request: Request) -> str | None:
    value = request.path_params.get("project_id")
    return value if isinstance(value, str) else None


def _is_api_request(request: Request) -> bool:
    path = request.url.path
    return path == "/api/v1" or path.startswith("/api/v1/")


def _is_locked(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message
