from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import read_project_metadata
from fastapi.testclient import TestClient

import novel_api.project_registry as project_registry_module

_UTC = timezone(timedelta(0))


def test_list_projects_discovers_immediate_story_dbs_and_metadata_states(
    client: TestClient, data_root: Path, project_factory
) -> None:
    project_factory(
        "alpha",
        working_title="Alpha",
        metadata={
            "project_id": "alpha",
            "status": "active",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    )
    archived_dir = project_factory(
        "archive-me",
        working_title="Archive Me",
        metadata={
            "project_id": "archive-me",
            "status": "archived",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    )
    missing_dir = project_factory("missing-meta", working_title="Missing Meta")
    malformed_dir = project_factory(
        "malformed-meta",
        working_title="Malformed Meta",
        metadata="{bad json",
    )
    project_factory(
        "broken-db",
        metadata={
            "project_id": "broken-db",
            "status": "active",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
        story_db_bytes=b"not a sqlite database",
    )
    project_factory("ignored", create_story_db=False)
    staging_dir = data_root / ".staging" / "token"
    staging_dir.mkdir(parents=True)
    project_factory_path = staging_dir / "story.db"
    project_factory_path.write_bytes(b"not discovered")
    nested_dir = data_root / "outer" / "nested"
    nested_dir.mkdir(parents=True)
    (nested_dir / "story.db").write_bytes(b"not discovered")

    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    body = response.json()
    projects = {item["project_id"]: item for item in body["projects"]}
    assert set(projects) == {"alpha", "broken-db", "malformed-meta", "missing-meta"}
    assert projects["alpha"] == {
        "project_id": "alpha",
        "status": "active",
        "metadata_state": "ok",
        "working_title": "Alpha",
        "created_at": "2026-08-28T00:00:00Z",
        "updated_at": "2026-08-28T00:00:00Z",
        "health": "ok",
    }
    assert projects["missing-meta"]["metadata_state"] == "missing"
    assert projects["missing-meta"]["status"] == "active"
    assert projects["missing-meta"]["working_title"] == "Missing Meta"
    assert projects["malformed-meta"]["metadata_state"] == "invalid"
    assert projects["malformed-meta"]["status"] == "active"
    assert projects["broken-db"]["health"] == "degraded"
    assert projects["broken-db"]["working_title"] is None
    assert not (missing_dir / "project.json").exists()
    assert (malformed_dir / "project.json").read_text(encoding="utf-8") == "{bad json"
    assert (archived_dir / "project.json").exists()

    archived_response = client.get(
        "/api/v1/projects", params={"include_archived": True}
    )

    assert archived_response.status_code == 200
    archived_ids = {item["project_id"] for item in archived_response.json()["projects"]}
    assert archived_ids == {
        "alpha",
        "archive-me",
        "broken-db",
        "malformed-meta",
        "missing-meta",
    }


def test_get_project_allows_archived_and_reports_invalid_metadata(
    client: TestClient, project_factory
) -> None:
    project_factory(
        "archive-me",
        working_title="Archive Me",
        metadata={
            "project_id": "archive-me",
            "status": "archived",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    )
    project_factory(
        "mismatch-meta",
        working_title="Mismatch",
        metadata={
            "project_id": "wrong-id",
            "status": "active",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    )

    archived_response = client.get("/api/v1/projects/archive-me")
    mismatch_response = client.get("/api/v1/projects/mismatch-meta")

    assert archived_response.status_code == 200
    assert archived_response.json()["status"] == "archived"
    assert archived_response.json()["working_title"] == "Archive Me"
    assert mismatch_response.status_code == 200
    assert mismatch_response.json()["project_id"] == "mismatch-meta"
    assert mismatch_response.json()["metadata_state"] == "invalid"
    assert mismatch_response.json()["status"] == "active"


def test_project_routes_reject_unknown_or_invalid_project_ids(
    client: TestClient,
) -> None:
    missing_response = client.get("/api/v1/projects/unknown-project")
    invalid_response = client.get("/api/v1/projects/Invalid")

    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_project_route_creates_explicit_project(
    client: TestClient, data_root: Path
) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"working_title": "冬東京", "project_id": "winter-tokyo"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == "winter-tokyo"
    assert body["status"] == "active"
    assert body["metadata_state"] == "ok"
    assert body["working_title"] == "冬東京"
    assert body["health"] == "ok"
    assert body["created_at"] is not None
    assert body["updated_at"] == body["created_at"]

    metadata = read_project_metadata(data_root / "winter-tokyo")
    assert metadata["project_id"] == "winter-tokyo"
    assert metadata["status"] == "active"


@pytest.mark.parametrize(
    "project_id",
    ["../escape", r"..\\escape", "alpha/beta", "alpha\\beta", "alpha ", "-alpha"],
)
def test_create_project_route_rejects_invalid_ids(
    client: TestClient, data_root: Path, project_id: str
) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"working_title": "Project", "project_id": project_id},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert list(data_root.iterdir()) == []


def test_create_project_route_reports_duplicate_conflict(
    client: TestClient, project_factory
) -> None:
    project_factory(
        "winter-tokyo",
        working_title="Original",
        metadata={
            "project_id": "winter-tokyo",
            "status": "active",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    )

    response = client.post(
        "/api/v1/projects",
        json={"working_title": "Duplicate", "project_id": "winter-tokyo"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT_CONFLICT"


def test_patch_project_status_hides_archived_projects_by_default(
    client: TestClient, project_factory
) -> None:
    project_factory(
        "winter-tokyo",
        working_title="Winter Tokyo",
        metadata={
            "project_id": "winter-tokyo",
            "status": "active",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    )

    archive_response = client.patch(
        "/api/v1/projects/winter-tokyo",
        json={"status": "archived"},
    )
    default_list_response = client.get("/api/v1/projects")
    archived_list_response = client.get(
        "/api/v1/projects", params={"include_archived": True}
    )
    archived_get_response = client.get("/api/v1/projects/winter-tokyo")
    restore_response = client.patch(
        "/api/v1/projects/winter-tokyo",
        json={"status": "active"},
    )
    restored_list_response = client.get("/api/v1/projects")

    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"
    assert default_list_response.json() == {"projects": []}
    assert archived_list_response.json()["projects"][0]["status"] == "archived"
    assert archived_get_response.json()["status"] == "archived"
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "active"
    assert restored_list_response.json()["projects"][0]["project_id"] == "winter-tokyo"


@pytest.mark.parametrize("metadata_kind", ["missing", "invalid"])
def test_patch_project_status_repairs_missing_or_invalid_metadata(
    client: TestClient,
    data_root: Path,
    project_factory,
    monkeypatch,
    metadata_kind: str,
) -> None:
    fixed_now = datetime(2026, 8, 28, 12, 34, 56, tzinfo=_UTC)
    monkeypatch.setattr(project_registry_module, "_utc_now", lambda: fixed_now)
    kwargs = {} if metadata_kind == "missing" else {"metadata": "{bad json"}
    project_factory("repair-me", working_title="Repair Me", **kwargs)

    response = client.patch("/api/v1/projects/repair-me", json={"status": "archived"})

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "repair-me"
    assert body["status"] == "archived"
    assert body["metadata_state"] == "ok"
    assert body["created_at"] == "2026-08-28T12:34:56Z"
    assert body["updated_at"] == "2026-08-28T12:34:56Z"

    metadata_file = read_project_metadata(data_root / "repair-me")
    assert metadata_file == {
        "project_id": "repair-me",
        "status": "archived",
        "created_at": "2026-08-28T12:34:56Z",
        "updated_at": "2026-08-28T12:34:56Z",
    }


def test_invalid_metadata_shapes_remain_visible_and_are_not_rewritten(
    client: TestClient, project_factory
) -> None:
    invalid_metadata = {
        "bad-status": {
            "project_id": "bad-status",
            "status": "paused",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
        "extra-field": {
            "project_id": "extra-field",
            "status": "active",
            "created_at": "2026-08-28T00:00:00Z",
            "updated_at": "2026-08-28T00:00:00Z",
            "health": "ok",
        },
        "bad-timestamp": {
            "project_id": "bad-timestamp",
            "status": "active",
            "created_at": "not-a-timestamp",
            "updated_at": "2026-08-28T00:00:00Z",
        },
        "loose-timestamp": {
            "project_id": "loose-timestamp",
            "status": "active",
            "created_at": "2026-8-28T0:0:0Z",
            "updated_at": "2026-08-28T00:00:00Z",
        },
    }
    metadata_paths = {}
    original_bytes = {}
    for project_id, metadata in invalid_metadata.items():
        project_dir = project_factory(project_id, metadata=metadata)
        metadata_paths[project_id] = project_dir / "project.json"
        original_bytes[project_id] = metadata_paths[project_id].read_bytes()

    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    projects = {item["project_id"]: item for item in response.json()["projects"]}
    assert set(projects) == set(invalid_metadata)
    for project_id in invalid_metadata:
        assert projects[project_id]["metadata_state"] == "invalid"
        assert projects[project_id]["status"] == "active"
        assert metadata_paths[project_id].read_bytes() == original_bytes[project_id]
