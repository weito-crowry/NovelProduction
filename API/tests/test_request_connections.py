from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from novel_core.repositories.search_repository import SearchRepository

import novel_api.project_registry as project_registry_module
import novel_api.service_container as service_container_module
from novel_api.app import create_app
from novel_api.config import ApiSettings
from novel_api.dependencies import resolve_project_target
from novel_api.service_container import ServiceContainer, open_project_services

SERVICE_FIELDS = (
    "work",
    "world_fact",
    "timeline",
    "character",
    "relationship",
    "canon",
    "search",
    "narrative",
    "character_state",
    "information",
    "disclosure",
    "knowledge",
    "episode_reference",
    "draft",
    "outline",
    "context",
)


class ObservedConnection:
    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self._raw.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


def _request_for(data_root: Path) -> Request:
    app = SimpleNamespace(
        state=SimpleNamespace(settings=ApiSettings(data_root=data_root))
    )
    scope: dict[str, Any] = {"type": "http", "app": app}
    return Request(scope)


def _service_connection(service: object) -> object:
    direct = getattr(service, "_connection", None)
    if direct is not None:
        return direct
    for value in vars(service).values():
        candidate = getattr(value, "_connection", None)
        if candidate is not None:
            return candidate
    raise AssertionError(f"could not locate connection for {type(service).__name__}")


def _create_test_app(data_root: Path) -> FastAPI:
    app = create_app(ApiSettings(data_root=data_root))
    router = APIRouter(prefix="/_test")

    @router.get("/probe/{project_id}")
    def probe_project(request: Request, project_id: str) -> dict[str, object]:
        target = resolve_project_target(request, project_id)
        with open_project_services(target) as services:
            return {
                "project_id": target.project_id,
                "working_title": services.work.get().working_title,
                "connection_ids": {
                    field_name: id(_service_connection(getattr(services, field_name)))
                    for field_name in SERVICE_FIELDS
                },
            }

    @router.get("/fail/{project_id}")
    def fail_project(request: Request, project_id: str) -> None:
        target = resolve_project_target(request, project_id)
        with open_project_services(target) as services:
            services.work.get()
            raise RuntimeError("boom")

    @router.get("/search/{project_id}")
    def search_project(request: Request, project_id: str) -> dict[str, object]:
        target = resolve_project_target(request, project_id)
        with open_project_services(target) as services:
            rows = services.search.search_world_facts("検索対象", 10)
            connection = _service_connection(services.search)
            return {
                "count": len(rows),
                "connection_id": id(connection),
                "in_transaction": bool(connection.in_transaction),
            }

    @router.post("/write/{project_id}")
    def write_project(request: Request, project_id: str) -> dict[str, object]:
        target = resolve_project_target(request, project_id)
        with open_project_services(target) as services:
            created = services.world_fact.create("新しい設定")
            connection = _service_connection(services.world_fact)
            return {
                "fact_id": created.id,
                "statement": created.statement,
                "connection_id": id(connection),
            }

    app.include_router(router)
    return app


def _install_connection_tracker(
    monkeypatch: pytest.MonkeyPatch,
) -> list[ObservedConnection]:
    observed: list[ObservedConnection] = []
    real_open_database = service_container_module.open_database

    def tracking_open_database(config: Any) -> ObservedConnection:
        connection = ObservedConnection(real_open_database(config))
        observed.append(connection)
        return connection

    monkeypatch.setattr(
        service_container_module, "open_database", tracking_open_database
    )
    monkeypatch.setattr(
        project_registry_module, "open_database", tracking_open_database
    )
    return observed


def test_resolve_project_target_returns_filesystem_metadata_without_opening_sqlite(
    data_root: Path, project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_factory("winter-tokyo", working_title="Winter Tokyo")

    def fail_open_database(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("resolve_project_target must not open SQLite")

    monkeypatch.setattr(project_registry_module, "open_database", fail_open_database)

    target = resolve_project_target(_request_for(data_root), "winter-tokyo")

    assert target.project_id == "winter-tokyo"
    assert target.descriptor.project_dir == data_root / "winter-tokyo"
    assert target.descriptor.story_db == data_root / "winter-tokyo" / "story.db"
    assert not hasattr(target, "connection")
    assert not hasattr(target.descriptor, "connection")


def test_project_requests_open_one_connection_share_it_across_all_services_and_close(
    data_root: Path, project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_factory("winter-tokyo", working_title="Winter Tokyo")
    observed = _install_connection_tracker(monkeypatch)

    with TestClient(_create_test_app(data_root)) as client:
        first_response = client.get("/_test/probe/winter-tokyo")
        assert first_response.status_code == 200
        assert len(observed) == 1
        assert observed[0].closed is True

        first_body = first_response.json()
        assert first_body["project_id"] == "winter-tokyo"
        assert first_body["working_title"] == "Winter Tokyo"
        assert set(first_body["connection_ids"]) == set(SERVICE_FIELDS)
        assert set(first_body["connection_ids"].values()) == {id(observed[0])}

        second_response = client.get("/_test/probe/winter-tokyo")
        assert second_response.status_code == 200
        assert len(observed) == 2
        assert observed[1].closed is True

        second_body = second_response.json()
        assert set(second_body["connection_ids"].values()) == {id(observed[1])}
        assert id(observed[0]) != id(observed[1])


def test_request_context_closes_connection_on_exception(
    data_root: Path, project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_factory("winter-tokyo", working_title="Winter Tokyo")
    observed = _install_connection_tracker(monkeypatch)

    with TestClient(
        _create_test_app(data_root),
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/_test/fail/winter-tokyo")

    assert response.status_code == 500
    assert len(observed) == 1
    assert observed[0].closed is True


def test_archived_projects_open_services_normally(
    data_root: Path, project_factory
) -> None:
    project_factory(
        "archive-me",
        working_title="Archived Project",
        metadata={
            "project_id": "archive-me",
            "status": "archived",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    )

    target = resolve_project_target(_request_for(data_root), "archive-me")
    with open_project_services(target) as services:
        assert isinstance(services, ServiceContainer)
        assert services.work.get().working_title == "Archived Project"


def test_unknown_projects_fail_before_any_database_open(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_open_database(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unknown project resolution must fail before DB open")

    monkeypatch.setattr(project_registry_module, "open_database", fail_open_database)

    with pytest.raises(HTTPException) as excinfo:
        resolve_project_target(_request_for(data_root), "unknown-project")

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "PROJECT_NOT_FOUND"


def test_open_project_services_preserves_sqlite_thread_affinity(
    data_root: Path, project_factory
) -> None:
    project_factory("threaded", working_title="Threaded")
    target = resolve_project_target(_request_for(data_root), "threaded")
    errors: list[BaseException] = []

    with open_project_services(target) as services:
        worker = threading.Thread(
            target=lambda: _use_service_in_other_thread(services, errors)
        )
        worker.start()
        worker.join()

    assert len(errors) == 1
    assert isinstance(errors[0], sqlite3.ProgrammingError)
    assert "same thread" in str(errors[0]).lower()


def _use_service_in_other_thread(
    services: ServiceContainer, errors: list[BaseException]
) -> None:
    try:
        services.work.get()
    except BaseException as exc:  # pragma: no cover - asserted by caller
        errors.append(exc)


def test_test_only_routes_search_then_write_succeeds_in_fresh_request_contexts(
    data_root: Path, project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_factory("winter-tokyo", working_title="Winter Tokyo")
    target = resolve_project_target(_request_for(data_root), "winter-tokyo")
    with open_project_services(target) as services:
        if not SearchRepository(_service_connection(services.search)).supports_trigram:
            pytest.skip("SQLite build does not provide FTS5 trigram")
        services.world_fact.create("検索対象の設定")

    observed = _install_connection_tracker(monkeypatch)

    with TestClient(_create_test_app(data_root)) as client:
        search_response = client.get("/_test/search/winter-tokyo")
        write_response = client.post("/_test/write/winter-tokyo")

    assert search_response.status_code == 200
    assert write_response.status_code == 200

    search_body = search_response.json()
    write_body = write_response.json()
    assert search_body["count"] == 1
    assert search_body["in_transaction"] is False
    assert write_body["statement"] == "新しい設定"
    assert search_body["connection_id"] != write_body["connection_id"]
    assert len(observed) == 2
    assert observed[0].closed is True
    assert observed[1].closed is True
