from __future__ import annotations

import importlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

VIEW_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/views/outline"),
    ("GET", "/api/v1/projects/{project_id}/views/dashboard"),
    ("GET", "/api/v1/projects/{project_id}/views/episodes/{episode_id}"),
}


def _data(response: Any, project_id: str = "view-project") -> Any:
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def _create_project(client: TestClient, project_id: str = "view-project") -> str:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": "View Project"},
    )
    assert response.status_code == 201, response.text
    return f"/api/v1/projects/{project_id}"


def _post(client: TestClient, path: str, payload: dict[str, Any]) -> Any:
    response = client.post(path, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _database_snapshot(story_db: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{story_db.as_posix()}?mode=ro", uri=True)
    try:
        table_names = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        return {
            "user_version": int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            ),
            "tables": {
                name: connection.execute(
                    f'SELECT * FROM "{name}" ORDER BY rowid'
                ).fetchall()
                for name in table_names
            },
        }
    finally:
        connection.close()


def _create_hierarchy(client: TestClient, base: str) -> dict[str, Any]:
    chapter_one = _post(client, f"{base}/chapters", {"title": "Chapter 1"})
    chapter_two = _post(client, f"{base}/chapters", {"title": "Chapter 2"})
    episode_one = _post(
        client,
        f"{base}/chapters/{chapter_one['id']}/episodes",
        {"title": "Episode 1"},
    )
    episode_two = _post(
        client,
        f"{base}/chapters/{chapter_one['id']}/episodes",
        {"title": "Episode 2"},
    )
    episode_three = _post(
        client,
        f"{base}/chapters/{chapter_two['id']}/episodes",
        {"title": "Episode 3"},
    )
    scene_one = _post(
        client,
        f"{base}/episodes/{episode_one['id']}/scenes",
        {"title": "Scene 1"},
    )
    scene_two = _post(
        client,
        f"{base}/episodes/{episode_one['id']}/scenes",
        {"title": "Scene 2"},
    )
    scene_three = _post(
        client,
        f"{base}/episodes/{episode_three['id']}/scenes",
        {"title": "Scene 3"},
    )
    return {
        "chapters": (chapter_one, chapter_two),
        "episodes": (episode_one, episode_two, episode_three),
        "scenes": (scene_one, scene_two, scene_three),
    }


def test_view_routes_are_exactly_registered(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]
    actual = {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if path.startswith("/api/v1/projects/{project_id}/views/")
    }

    assert actual == VIEW_OPERATIONS


def test_outline_and_dashboard_preserve_order_and_do_not_mutate_database(
    client: TestClient, data_root: Path
) -> None:
    base = _create_project(client)
    hierarchy = _create_hierarchy(client, base)
    story_db = data_root / "view-project" / "story.db"
    before = _database_snapshot(story_db)

    outline = _data(client.get(f"{base}/views/outline"))
    dashboard = _data(client.get(f"{base}/views/dashboard"))

    assert [item["chapter"]["id"] for item in outline["chapters"]] == [
        item["id"] for item in hierarchy["chapters"]
    ]
    assert [item["episode"]["id"] for item in outline["chapters"][0]["episodes"]] == [
        hierarchy["episodes"][0]["id"],
        hierarchy["episodes"][1]["id"],
    ]
    assert [item["id"] for item in outline["chapters"][0]["episodes"][0]["scenes"]] == [
        hierarchy["scenes"][0]["id"],
        hierarchy["scenes"][1]["id"],
    ]
    assert dashboard["work"]["working_title"] == "View Project"
    assert dashboard["chapter_count"] == 2
    assert dashboard["episode_count"] == 3
    assert dashboard["scene_count"] == 3
    assert _database_snapshot(story_db) == before


def test_episode_view_composes_existing_reads_and_missing_draft_is_null(
    client: TestClient, data_root: Path
) -> None:
    base = _create_project(client)
    hierarchy = _create_hierarchy(client, base)
    episode = hierarchy["episodes"][0]
    episode_id = episode["id"]
    story_db = data_root / "view-project" / "story.db"
    before = _database_snapshot(story_db)

    view = _data(client.get(f"{base}/views/episodes/{episode_id}"))

    assert view["episode"] == _data(client.get(f"{base}/episodes/{episode_id}"))
    assert view["scenes"] == _data(client.get(f"{base}/episodes/{episode_id}/scenes"))
    assert view["episode_references"] == _data(
        client.get(f"{base}/episodes/{episode_id}/references")
    )
    assert view["outline"] == _data(client.get(f"{base}/episodes/{episode_id}/outline"))
    assert view["context"] == _data(client.get(f"{base}/episodes/{episode_id}/context"))
    assert view["latest_draft"] is None
    assert view["recent_draft_history"] == []
    assert _database_snapshot(story_db) == before


def test_episode_view_returns_latest_draft_and_only_twenty_recent_revisions(
    client: TestClient,
) -> None:
    base = _create_project(client)
    hierarchy = _create_hierarchy(client, base)
    episode_id = hierarchy["episodes"][0]["id"]
    parent_id: int | None = None
    latest: dict[str, Any] | None = None
    for revision in range(1, 23):
        payload: dict[str, Any] = {"body": f"draft {revision}"}
        if parent_id is not None:
            payload["expected_parent_draft_id"] = parent_id
        latest = _post(client, f"{base}/episodes/{episode_id}/drafts", payload)
        parent_id = latest["id"]

    view = _data(client.get(f"{base}/views/episodes/{episode_id}"))

    assert latest is not None
    assert view["latest_draft"] == latest
    assert [item["revision"] for item in view["recent_draft_history"]] == list(
        range(3, 23)
    )
    assert all("body" not in item for item in view["recent_draft_history"])


def test_episode_view_preserves_fine_grained_future_disclosure_guards(
    client: TestClient,
) -> None:
    base = _create_project(client)
    chapter = _post(client, f"{base}/chapters", {"title": "Chapter"})
    target = _post(
        client,
        f"{base}/chapters/{chapter['id']}/episodes",
        {"title": "Target"},
    )
    future = _post(
        client,
        f"{base}/chapters/{chapter['id']}/episodes",
        {"title": "Future"},
    )
    character = _post(client, f"{base}/characters", {"display_name": "Hero"})
    secret = _post(
        client,
        f"{base}/information",
        {
            "statement": "SECRET_DERIVED_VIEW_BODY",
            "authoring_guard": "Do not reveal the future secret",
        },
    )
    for reference_type, target_id in (
        ("character", character["id"]),
        ("information", secret["id"]),
    ):
        _post(
            client,
            f"{base}/episodes/{target['id']}/references",
            {"reference_type": reference_type, "target_id": target_id},
        )
    assert (
        client.put(
            f"{base}/information/{secret['id']}/reader-disclosure",
            json={"episode_id": future["id"]},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{base}/characters/{character['id']}/knowledge/{secret['id']}",
            json={"episode_id": target["id"], "knowledge_state": "knows"},
        ).status_code
        == 200
    )

    view = _data(client.get(f"{base}/views/episodes/{target['id']}"))
    fine_outline = _data(client.get(f"{base}/episodes/{target['id']}/outline"))
    fine_context = _data(client.get(f"{base}/episodes/{target['id']}/context"))

    assert view["outline"] == fine_outline
    assert view["context"] == fine_context
    assert fine_outline["references"]["information"] == []
    assert fine_context["participants"][0]["known_information"] == []
    assert "SECRET_DERIVED_VIEW_BODY" not in json.dumps(view, ensure_ascii=False)


def test_each_view_handler_resolves_and_opens_real_services_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        views = importlib.import_module("novel_api.routes.views")
    except ModuleNotFoundError:
        pytest.fail("views router is not implemented")
    base = _create_project(client)
    hierarchy = _create_hierarchy(client, base)
    episode_id = hierarchy["episodes"][0]["id"]
    calls = {"resolve": 0, "open": 0}
    original_resolve = views.resolve_project_target
    original_open = views.open_project_services

    def counting_resolve(*args: Any, **kwargs: Any) -> Any:
        calls["resolve"] += 1
        return original_resolve(*args, **kwargs)

    @contextmanager
    def counting_open(*args: Any, **kwargs: Any) -> Iterator[Any]:
        calls["open"] += 1
        with original_open(*args, **kwargs) as services:
            yield services

    monkeypatch.setattr(views, "resolve_project_target", counting_resolve)
    monkeypatch.setattr(views, "open_project_services", counting_open)

    assert client.get(f"{base}/views/outline").status_code == 200
    assert client.get(f"{base}/views/dashboard").status_code == 200
    assert client.get(f"{base}/views/episodes/{episode_id}").status_code == 200
    assert calls == {"resolve": 3, "open": 3}
