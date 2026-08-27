from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from novel_core.errors import (
    CanonPolicyError,
    CanonReasonRequired,
    DeprecatedCanonForbiddenError,
    RelationshipIntegrityError,
    ValidationError,
    VersionConflictError,
    WorkScopeError,
)


def json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_values = asdict(value)
        return {key: json_value(item) for key, item in dataclass_values.items()}
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [json_value(item) for item in value]
    return value


def success(value: Any) -> dict[str, Any]:
    return {"ok": True, "data": json_value(value)}


def error_payload(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, CanonReasonRequired):
        code = "CANON_REASON_REQUIRED"
    elif isinstance(exc, DeprecatedCanonForbiddenError):
        code = "DEPRECATED_CANON_FORBIDDEN"
    elif isinstance(exc, CanonPolicyError):
        code = "CANON_POLICY_ERROR"
    elif isinstance(exc, RelationshipIntegrityError):
        code = "RELATION_INTEGRITY_ERROR"
    elif isinstance(exc, VersionConflictError):
        code = "VERSION_CONFLICT"
    elif isinstance(exc, WorkScopeError):
        code = "WORK_SCOPE_ERROR"
    elif isinstance(exc, ValidationError) or isinstance(exc, ValueError):
        code = "VALIDATION_ERROR"
    elif isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
        code = "DATABASE_BUSY"
    elif isinstance(exc, sqlite3.IntegrityError):
        code = "RELATION_INTEGRITY_ERROR"
    elif exc.__class__.__name__.endswith("NotFoundError"):
        code = "NOT_FOUND"
    elif exc.__class__.__name__ == "OrderConflictError":
        code = "ORDER_CONFLICT"
    else:
        code = "INTERNAL_ERROR"
    field = getattr(exc, "field", None)
    detail = {"field": field} if field is not None else {}
    return {
        "ok": False,
        "error": {"code": code, "message": _safe_message(exc), **detail},
    }


def _safe_message(exc: BaseException) -> str:
    if isinstance(exc, sqlite3.Error):
        return "database operation failed"
    if isinstance(exc, ValidationError | ValueError):
        return getattr(exc, "message", str(exc)).removeprefix("VALIDATION_ERROR: ")
    if isinstance(exc, CanonReasonRequired | CanonPolicyError | VersionConflictError):
        return str(exc).split(": ", 1)[-1]
    if isinstance(exc, DeprecatedCanonForbiddenError):
        return "deprecated canon cannot be used as active context"
    if isinstance(exc, WorkScopeError):
        return str(exc).split(": ", 1)[-1]
    if exc.__class__.__name__.endswith("NotFoundError"):
        return "requested entity was not found"
    if exc.__class__.__name__ == "OrderConflictError":
        return "requested order conflicts with existing data"
    return "internal server error"
