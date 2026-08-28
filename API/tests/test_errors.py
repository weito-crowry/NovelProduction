from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from novel_core.errors import (
    CanonDecisionNotFoundError,
    CanonEntityNotFoundError,
    CanonPolicyError,
    CanonReasonRequired,
    CharacterNotFoundError,
    DeprecatedCanonForbiddenError,
    NarrativeNotFoundError,
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

from novel_api.app import create_app
from novel_api.config import ApiSettings
from novel_api.errors import build_conflict_details
from novel_api.project_registry import ProjectNotFoundError
from novel_api.schemas.common import ProjectEnvelope
from novel_api.serialization import serialize_value


def _app_raising(data_root: Any, exc: BaseException, *, project_scope: bool) -> FastAPI:
    app = create_app(ApiSettings(data_root=data_root))

    if project_scope:

        @app.get("/api/v1/_test/{project_id}/failure")
        def raise_project_error(project_id: str) -> None:
            del project_id
            raise exc

    else:

        @app.get("/api/v1/_test/failure")
        def raise_unscoped_error() -> None:
            raise exc

    return app


@pytest.mark.parametrize(
    ("exc", "status_code", "code", "domain_code"),
    [
        (
            ValidationError("unsafe validation detail"),
            400,
            "VALIDATION_ERROR",
            "VALIDATION_ERROR",
        ),
        (ValueError("unsafe value detail"), 400, "VALIDATION_ERROR", None),
        (ProjectNotFoundError("unsafe project path"), 404, "PROJECT_NOT_FOUND", None),
        (WorkScopeError("unsafe scope detail"), 404, "NOT_FOUND", "WORK_SCOPE_ERROR"),
        (
            VersionConflictError("VERSION_CONFLICT expected=99 current=100"),
            409,
            "VERSION_CONFLICT",
            "VersionConflictError",
        ),
        (
            OrderConflictError("unsafe order detail"),
            409,
            "ORDER_CONFLICT",
            "ORDER_CONFLICT",
        ),
        (
            RelationshipIntegrityError("unsafe relationship detail"),
            409,
            "DEPENDENCY_CONFLICT",
            "RELATION_INTEGRITY_ERROR",
        ),
        (
            CanonPolicyError("unsafe canon detail"),
            409,
            "DEPENDENCY_CONFLICT",
            "CANON_POLICY_ERROR",
        ),
        (
            CanonReasonRequired("unsafe canon reason detail"),
            409,
            "DEPENDENCY_CONFLICT",
            "CANON_REASON_REQUIRED",
        ),
        (
            DeprecatedCanonForbiddenError("unsafe deprecated canon detail"),
            409,
            "DEPENDENCY_CONFLICT",
            "DEPRECATED_CANON_FORBIDDEN",
        ),
        (
            sqlite3.IntegrityError("UNIQUE constraint failed: secrets.token"),
            409,
            "DEPENDENCY_CONFLICT",
            None,
        ),
        (
            sqlite3.OperationalError("database is locked; SELECT secret FROM tokens"),
            503,
            "DATABASE_BUSY",
            None,
        ),
        (
            sqlite3.OperationalError("no such table: secret_tokens"),
            500,
            "INTERNAL_ERROR",
            None,
        ),
    ],
    ids=[
        "core-validation",
        "value-error",
        "project-not-found",
        "work-scope",
        "version-conflict",
        "order-conflict",
        "relationship-integrity",
        "canon-policy",
        "canon-reason-required",
        "deprecated-canon-forbidden",
        "sqlite-integrity",
        "sqlite-locked",
        "sqlite-unexpected-operational",
    ],
)
def test_api_exception_mappings_are_structured_and_sanitized(
    tmp_path: Any,
    exc: BaseException,
    status_code: int,
    code: str,
    domain_code: str | None,
) -> None:
    app = _app_raising(tmp_path, exc, project_scope=True)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/_test/winter-tokyo/failure")

    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["project_id"] == "winter-tokyo"
    assert body["error"]["details"] == (
        {} if domain_code is None else {"domain_code": domain_code}
    )
    serialized = response.text.lower()
    for secret in ("unsafe", "select", "unique", "secret", "traceback"):
        assert secret not in serialized


@pytest.mark.parametrize(
    "exc",
    [
        WorkNotFoundError("unsafe"),
        WorldFactNotFoundError("unsafe"),
        TimelineEventNotFoundError("unsafe"),
        CharacterNotFoundError("unsafe"),
        RelationshipNotFoundError("unsafe"),
        NarrativeNotFoundError("unsafe"),
        CanonDecisionNotFoundError("unsafe"),
        CanonEntityNotFoundError("unsafe"),
    ],
    ids=lambda exc: type(exc).__name__,
)
def test_every_core_not_found_error_maps_to_not_found(
    tmp_path: Any, exc: BaseException
) -> None:
    app = _app_raising(tmp_path, exc, project_scope=True)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/_test/winter-tokyo/failure")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested resource was not found.",
            "project_id": "winter-tokyo",
            "details": {"domain_code": getattr(exc, "code", type(exc).__name__)},
        }
    }


def test_request_validation_error_uses_400_contract_without_project_scope(
    tmp_path: Any,
) -> None:
    app = create_app(ApiSettings(data_root=tmp_path))

    @app.get("/api/v1/_test/validation")
    def validate_query(count: int) -> dict[str, int]:
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/api/v1/_test/validation", params={"count": "bad"})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "The request is invalid.",
            "project_id": None,
            "details": {},
        }
    }


def test_unexpected_api_exception_is_sanitized_and_unscoped(tmp_path: Any) -> None:
    app = _app_raising(
        tmp_path,
        RuntimeError("TRACEBACK secret implementation detail"),
        project_scope=False,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/_test/failure")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal server error occurred.",
            "project_id": None,
            "details": {},
        }
    }
    assert "secret" not in response.text.lower()
    assert "traceback" not in response.text.lower()


def test_non_api_exception_keeps_default_non_json_behavior(tmp_path: Any) -> None:
    app = create_app(ApiSettings(data_root=tmp_path))

    @app.get("/outside/failure")
    def raise_outside_api() -> None:
        raise RuntimeError("outside failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/outside/failure")

    assert response.status_code == 500
    assert not response.headers["content-type"].startswith("application/json")
    assert response.text == "Internal Server Error"


def test_health_contract_is_unchanged_after_error_handler_installation(
    tmp_path: Any,
) -> None:
    app = create_app(ApiSettings(data_root=tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "v1"}


@dataclass(frozen=True, slots=True)
class ExampleRecord:
    id: int
    labels: tuple[str, ...]
    details_json: str


def test_project_envelope_and_serializer_preserve_core_shaped_values() -> None:
    serialized = serialize_value(
        ExampleRecord(id=14, labels=("draft", "canon"), details_json='{"key": 1}')
    )
    envelope = ProjectEnvelope[dict[str, Any]](
        project_id="winter-tokyo", data=serialized
    )

    assert envelope.model_dump() == {
        "project_id": "winter-tokyo",
        "data": {
            "id": 14,
            "labels": ["draft", "canon"],
            "details_json": '{"key": 1}',
        },
    }


@pytest.mark.parametrize("unsafe_value", [RuntimeError("secret exception")])
def test_serializer_rejects_raw_exceptions(unsafe_value: object) -> None:
    with pytest.raises(TypeError, match="not JSON serializable"):
        serialize_value(unsafe_value)


def test_serializer_rejects_sqlite_connections() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(TypeError, match="not JSON serializable"):
            serialize_value({"connection": connection})
    finally:
        connection.close()


def test_conflict_details_use_explicit_values_and_resource() -> None:
    details = build_conflict_details(
        entity_type="episode",
        entity_id=14,
        expected_version=4,
        current_version=5,
        current_resource=ExampleRecord(
            id=14, labels=("canon",), details_json='{"safe": true}'
        ),
    )

    assert details == {
        "entity_type": "episode",
        "entity_id": 14,
        "expected_version": 4,
        "current_version": 5,
        "current_resource": {
            "id": 14,
            "labels": ["canon"],
            "details_json": '{"safe": true}',
        },
    }


def test_conflict_details_can_use_caller_supplied_safe_read_callback() -> None:
    calls = 0

    def safe_read() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"id": 14, "version": 5}

    details = build_conflict_details(
        entity_type="episode",
        entity_id=14,
        expected_version=4,
        current_version=5,
        read_current=safe_read,
    )

    assert calls == 1
    assert details["current_resource"] == {"id": 14, "version": 5}


def test_version_conflict_fallback_does_not_parse_exception_text(tmp_path: Any) -> None:
    app = _app_raising(
        tmp_path,
        VersionConflictError("VERSION_CONFLICT expected=999 current=1000"),
        project_scope=True,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/_test/winter-tokyo/failure")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "VERSION_CONFLICT",
            "message": "The resource was modified by another client.",
            "project_id": "winter-tokyo",
            "details": {"domain_code": "VersionConflictError"},
        }
    }
    assert "999" not in response.text
    assert "1000" not in response.text
