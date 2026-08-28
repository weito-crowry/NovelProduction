from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import novel_api.cli as cli
from novel_api.app import create_app
from novel_api.config import ApiSettings


def _create_project(client: TestClient, project_id: str, title: str) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": title},
    )
    assert response.status_code == 201, response.text
    assert response.json()["project_id"] == project_id


def _data(response: Any, project_id: str, status_code: int = 200) -> Any:
    assert response.status_code == status_code, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def _listed_project_ids(
    client: TestClient, *, include_archived: bool = False
) -> set[str]:
    response = client.get(
        "/api/v1/projects",
        params={"include_archived": str(include_archived).lower()},
    )
    assert response.status_code == 200, response.text
    return {project["project_id"] for project in response.json()["projects"]}


def test_alpha_and_beta_keep_colliding_numeric_ids_isolated(
    client: TestClient,
) -> None:
    _create_project(client, "alpha", "Alpha")
    _create_project(client, "beta", "Beta")

    alpha_fact = _data(
        client.post(
            "/api/v1/projects/alpha/world-facts",
            json={"statement": "ALPHA_ONLY_SETTING"},
        ),
        "alpha",
        201,
    )
    beta_fact = _data(
        client.post(
            "/api/v1/projects/beta/world-facts",
            json={"statement": "BETA_ONLY_SETTING"},
        ),
        "beta",
        201,
    )

    assert alpha_fact["id"] == beta_fact["id"] == 1
    assert (
        _data(
            client.get(f"/api/v1/projects/alpha/world-facts/{alpha_fact['id']}"),
            "alpha",
        )["statement"]
        == "ALPHA_ONLY_SETTING"
    )
    assert (
        _data(
            client.get(f"/api/v1/projects/beta/world-facts/{beta_fact['id']}"),
            "beta",
        )["statement"]
        == "BETA_ONLY_SETTING"
    )
    assert (
        _data(
            client.get(
                "/api/v1/projects/alpha/world-facts/search",
                params={"query": "BETA_ONLY_SETTING"},
            ),
            "alpha",
        )
        == []
    )
    assert (
        _data(
            client.get(
                "/api/v1/projects/beta/world-facts/search",
                params={"query": "ALPHA_ONLY_SETTING"},
            ),
            "beta",
        )
        == []
    )


def test_stale_work_update_returns_latest_snapshot_and_preserves_winner(
    client: TestClient,
) -> None:
    _create_project(client, "alpha", "Alpha")
    work_url = "/api/v1/projects/alpha/work"
    original = _data(client.get(work_url), "alpha")

    client_a = _data(
        client.patch(
            work_url,
            json={
                "working_title": "Alpha from client A",
                "expected_version": original["version"],
            },
        ),
        "alpha",
    )
    client_b = client.patch(
        work_url,
        json={
            "working_title": "Alpha from stale client B",
            "expected_version": original["version"],
        },
    )

    assert client_b.status_code == 409
    assert client_b.json()["error"] == {
        "code": "VERSION_CONFLICT",
        "message": "The resource was modified by another client.",
        "project_id": "alpha",
        "details": {
            "entity_type": "work",
            "entity_id": client_a["id"],
            "expected_version": original["version"],
            "current_version": client_a["version"],
            "current_resource": client_a,
            "domain_code": "VersionConflictError",
        },
    }
    assert _data(client.get(work_url), "alpha") == client_a


def test_archived_project_is_hidden_but_explicitly_readable_and_writable(
    client: TestClient,
) -> None:
    _create_project(client, "alpha", "Alpha")
    project_url = "/api/v1/projects/alpha"
    work_url = f"{project_url}/work"

    archived = client.patch(project_url, json={"status": "archived"})
    assert archived.status_code == 200, archived.text
    assert archived.json()["project_id"] == "alpha"
    assert archived.json()["status"] == "archived"
    assert "alpha" not in _listed_project_ids(client)
    assert "alpha" in _listed_project_ids(client, include_archived=True)

    current = _data(client.get(work_url), "alpha")
    updated = _data(
        client.patch(
            work_url,
            json={
                "working_title": "Archived Alpha remains writable",
                "expected_version": current["version"],
            },
        ),
        "alpha",
    )
    assert updated["working_title"] == "Archived Alpha remains writable"

    restored = client.patch(project_url, json={"status": "active"})
    assert restored.status_code == 200, restored.text
    assert restored.json()["project_id"] == "alpha"
    assert restored.json()["status"] == "active"
    assert "alpha" in _listed_project_ids(client)


def test_development_cors_allows_only_the_configured_exact_origin(
    data_root: Path,
) -> None:
    allowed_origin = "http://127.0.0.1:5173"
    app = create_app(ApiSettings(data_root=data_root, dev_cors_origin=allowed_origin))
    with TestClient(app) as cors_client:
        allowed = cors_client.get("/api/v1/health", headers={"Origin": allowed_origin})
        denied = cors_client.get(
            "/api/v1/health", headers={"Origin": "http://192.0.2.10:5173"}
        )

    assert allowed.headers["access-control-allow-origin"] == allowed_origin
    assert allowed.headers["access-control-allow-origin"] != "*"
    assert "access-control-allow-origin" not in denied.headers

    without_cors = create_app(ApiSettings(data_root=data_root))
    with TestClient(without_cors) as no_cors_client:
        unconfigured = no_cors_client.get(
            "/api/v1/health", headers={"Origin": allowed_origin}
        )
    assert "access-control-allow-origin" not in unconfigured.headers


def test_development_cors_rejects_wildcard_origin(data_root: Path) -> None:
    with pytest.raises(ValueError, match="wildcard"):
        create_app(ApiSettings(data_root=data_root, dev_cors_origin="*"))


def test_bind_failure_propagates_without_port_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []

    def fail_bind(app: object, **kwargs: object) -> None:
        calls.append({"app": app, **kwargs})
        raise OSError("configured port is already in use")

    monkeypatch.setattr(cli.uvicorn, "run", fail_bind)

    with pytest.raises(OSError, match="configured port is already in use"):
        cli.main(
            [
                "--data-root",
                str(tmp_path / "sandbox-data"),
                "--host",
                "127.0.0.1",
                "--port",
                "9876",
            ]
        )

    assert len(calls) == 1
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 9876
