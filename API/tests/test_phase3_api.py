from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

PHASE3_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/episodes/{episode_id}/outline"),
    ("GET", "/api/v1/projects/{project_id}/episodes/{episode_id}/context"),
    ("GET", "/api/v1/projects/{project_id}/episodes/{episode_id}/draft"),
    ("POST", "/api/v1/projects/{project_id}/episodes/{episode_id}/drafts"),
    ("GET", "/api/v1/projects/{project_id}/episodes/{episode_id}/drafts"),
}


def _phase3_operations(app: FastAPI) -> set[tuple[str, str]]:
    paths = app.openapi()["paths"]
    return {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if (method.upper(), path) in PHASE3_OPERATIONS
    }


def _data(response: Any, project_id: str = "phase-three") -> Any:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def _create_project(client: TestClient, project_id: str = "phase-three") -> str:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": "第三部"},
    )
    assert response.status_code == 201
    return f"/api/v1/projects/{project_id}"


def _create_episode(
    client: TestClient, base: str, title: str = "対象話"
) -> dict[str, Any]:
    chapter = _data(
        client.post(f"{base}/chapters", json={"title": "章"}),
        base.rsplit("/", 1)[-1],
    )
    return _data(
        client.post(
            f"{base}/chapters/{chapter['id']}/episodes",
            json={"title": title},
        ),
        base.rsplit("/", 1)[-1],
    )


def test_phase3_registers_exactly_all_five_operations(client: TestClient) -> None:
    assert len(PHASE3_OPERATIONS) == 5
    assert _phase3_operations(client.app) == PHASE3_OPERATIONS


def test_each_phase3_handler_resolves_and_opens_services_exactly_once() -> None:
    route_path = (
        Path(__file__).parents[1] / "src" / "novel_api" / "routes" / "authoring.py"
    )
    module = ast.parse(route_path.read_text(encoding="utf-8"))
    handlers = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and any(isinstance(item, ast.Call) for item in node.decorator_list)
    ]

    assert len(handlers) == 5
    for handler in handlers:
        calls = [
            node.func.id
            for node in ast.walk(handler)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        methods = {
            decorator.func.attr.upper()
            for decorator in handler.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
        }
        assert calls.count("resolve_project_target") == 1, handler.name
        expected_context = (
            "open_project_read_services"
            if "GET" in methods
            else "open_project_services"
        )
        assert calls.count(expected_context) == 1, handler.name


def test_outline_and_context_preserve_future_disclosure_guards(
    client: TestClient,
) -> None:
    base = _create_project(client)
    chapter = _data(client.post(f"{base}/chapters", json={"title": "章"}))
    target = _data(
        client.post(
            f"{base}/chapters/{chapter['id']}/episodes",
            json={"title": "対象話"},
        )
    )
    future = _data(
        client.post(
            f"{base}/chapters/{chapter['id']}/episodes",
            json={"title": "未来話"},
        )
    )
    character = _data(
        client.post(f"{base}/characters", json={"display_name": "主人公"})
    )
    secret = _data(
        client.post(
            f"{base}/information",
            json={
                "statement": "SECRET_FUTURE_BODY_PHASE3",
                "authoring_guard": "未来の秘密を開示しない",
            },
        )
    )
    for reference_type, target_id in (
        ("character", character["id"]),
        ("information", secret["id"]),
    ):
        _data(
            client.post(
                f"{base}/episodes/{target['id']}/references",
                json={"reference_type": reference_type, "target_id": target_id},
            )
        )
    _data(
        client.put(
            f"{base}/information/{secret['id']}/reader-disclosure",
            json={"episode_id": future["id"]},
        )
    )
    _data(
        client.put(
            f"{base}/characters/{character['id']}/knowledge/{secret['id']}",
            json={
                "episode_id": target["id"],
                "knowledge_state": "knows",
            },
        )
    )
    _data(
        client.put(
            f"{base}/characters/{character['id']}/states/{future['id']}",
            json={"physical_state": "SECRET_FUTURE_STATE_PHASE3"},
        )
    )

    outline = _data(client.get(f"{base}/episodes/{target['id']}/outline"))
    context = _data(client.get(f"{base}/episodes/{target['id']}/context"))
    serialized = json.dumps(
        {"outline": outline, "context": context}, ensure_ascii=False
    )

    assert outline["episode"]["id"] == target["id"]
    assert context["episode"]["id"] == target["id"]
    assert outline["references"]["information"] == []
    assert context["participants"][0]["known_information"] == []
    assert context["participants"][0]["effective_state"] is None
    assert outline["protected_information_guards"][0]["guard_text"] == (
        "未来の秘密を開示しない"
    )
    assert "SECRET_FUTURE_BODY_PHASE3" not in serialized
    assert "SECRET_FUTURE_STATE_PHASE3" not in serialized


def test_absent_draft_is_null_and_revision_query_is_validated(
    client: TestClient,
) -> None:
    base = _create_project(client)
    episode = _create_episode(client, base)

    assert _data(client.get(f"{base}/episodes/{episode['id']}/draft")) is None
    invalid = client.get(
        f"{base}/episodes/{episode['id']}/draft", params={"revision": 0}
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_draft_saves_are_plain_append_only_and_history_is_metadata_only(
    client: TestClient,
) -> None:
    base = _create_project(client)
    episode = _create_episode(client, base)
    draft_url = f"{base}/episodes/{episode['id']}/drafts"

    first = _data(
        client.post(
            draft_url,
            json={
                "body": "\n  第一稿\n",
                "source_agent": "human",
                "change_summary": "初稿",
            },
        )
    )
    second = _data(
        client.post(
            draft_url,
            json={
                "body": "第二稿",
                "expected_parent_draft_id": first["id"],
            },
        )
    )

    assert first["revision"] == 1
    assert first["parent_draft_id"] is None
    assert first["body"] == "\n  第一稿\n"
    assert second["revision"] == 2
    assert second["parent_draft_id"] == first["id"]
    assert (
        _data(
            client.get(f"{base}/episodes/{episode['id']}/draft", params={"revision": 1})
        )
        == first
    )
    assert _data(client.get(f"{base}/episodes/{episode['id']}/draft")) == second

    history = _data(client.get(draft_url))
    assert [item["revision"] for item in history] == [1, 2]
    assert history[0]["body_chars"] == len(first["body"])
    assert "body" not in history[0]
    assert history[1]["change_summary"] == ""


def test_stale_parent_returns_latest_snapshot_without_appending(
    client: TestClient,
) -> None:
    base = _create_project(client)
    episode = _create_episode(client, base)
    draft_url = f"{base}/episodes/{episode['id']}/drafts"
    first = _data(client.post(draft_url, json={"body": "first"}))
    latest = _data(
        client.post(
            draft_url,
            json={
                "body": "latest",
                "expected_parent_draft_id": first["id"],
            },
        )
    )

    response = client.post(
        draft_url,
        json={"body": "stale", "expected_parent_draft_id": first["id"]},
    )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "VERSION_CONFLICT",
        "message": "The resource was modified by another client.",
        "project_id": "phase-three",
        "details": {
            "entity_type": "draft",
            "entity_id": episode["id"],
            "expected_version": first["id"],
            "current_version": latest["id"],
            "current_resource": latest,
            "domain_code": "VersionConflictError",
        },
    }
    assert [item["revision"] for item in _data(client.get(draft_url))] == [1, 2]
    assert _data(client.get(f"{base}/episodes/{episode['id']}/draft")) == latest


def test_draft_save_accepts_only_bounded_plain_body_fields(
    client: TestClient,
) -> None:
    base = _create_project(client)
    episode = _create_episode(client, base)
    draft_url = f"{base}/episodes/{episode['id']}/drafts"

    invalid_payloads = (
        {"body": ""},
        {"body": {"schema_version": 1, "content": []}},
        {"body": "text", "expected_parent_draft_id": 0},
        {"body": "text", "source_agent": ""},
        {"body": "text", "source_agent": "a" * 121},
        {"body": "text", "change_summary": "a" * 1001},
        {"body": "text", "document_json": {"schema_version": 1}},
    )
    for payload in invalid_payloads:
        response = client.post(draft_url, json=payload)
        assert response.status_code == 400, payload
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_phase3_cross_project_episode_ids_are_not_read_or_written(
    client: TestClient,
) -> None:
    base_a = _create_project(client, "project-a")
    episode_a = _create_episode(client, base_a, "A話")
    base_b = _create_project(client, "project-b")

    responses = (
        client.get(f"{base_b}/episodes/{episode_a['id']}/outline"),
        client.get(f"{base_b}/episodes/{episode_a['id']}/context"),
        client.get(f"{base_b}/episodes/{episode_a['id']}/draft"),
        client.get(f"{base_b}/episodes/{episode_a['id']}/drafts"),
        client.post(
            f"{base_b}/episodes/{episode_a['id']}/drafts",
            json={"body": "foreign write"},
        ),
    )
    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
