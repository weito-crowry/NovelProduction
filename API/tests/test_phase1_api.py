from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from novel_core.services.search_service import SearchService

PHASE1_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/work"),
    ("PATCH", "/api/v1/projects/{project_id}/work"),
    ("POST", "/api/v1/projects/{project_id}/world-facts"),
    ("GET", "/api/v1/projects/{project_id}/world-facts/search"),
    ("GET", "/api/v1/projects/{project_id}/world-facts/{fact_id}"),
    ("PATCH", "/api/v1/projects/{project_id}/world-facts/{fact_id}"),
    ("POST", "/api/v1/projects/{project_id}/timeline/events"),
    ("GET", "/api/v1/projects/{project_id}/timeline/events/search"),
    ("GET", "/api/v1/projects/{project_id}/timeline/events/{event_id}"),
    ("PATCH", "/api/v1/projects/{project_id}/timeline/events/{event_id}"),
    ("GET", "/api/v1/projects/{project_id}/timeline/range"),
    ("POST", "/api/v1/projects/{project_id}/timeline/events/{event_id}/move"),
    ("POST", "/api/v1/projects/{project_id}/timeline/relations"),
    ("POST", "/api/v1/projects/{project_id}/characters"),
    ("GET", "/api/v1/projects/{project_id}/characters/search"),
    ("GET", "/api/v1/projects/{project_id}/characters/{character_id}"),
    ("PATCH", "/api/v1/projects/{project_id}/characters/{character_id}"),
    ("POST", "/api/v1/projects/{project_id}/relationships"),
    ("PATCH", "/api/v1/projects/{project_id}/relationships/{relationship_id}"),
    ("GET", "/api/v1/projects/{project_id}/relationships"),
    ("POST", "/api/v1/projects/{project_id}/canon/status"),
    ("GET", "/api/v1/projects/{project_id}/canon/decisions/search"),
    ("GET", "/api/v1/projects/{project_id}/canon/decisions/{decision_id}"),
}


def _phase1_operations(app: FastAPI) -> set[tuple[str, str]]:
    paths = app.openapi()["paths"]
    return {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if (method.upper(), path) in PHASE1_OPERATIONS
    }


def _data(response: Any, project_id: str = "phase-one") -> Any:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def _create_project(client: TestClient, project_id: str = "phase-one") -> None:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": "第一部"},
    )
    assert response.status_code == 201


def test_phase1_registers_exactly_all_23_operations(client: TestClient) -> None:
    assert len(PHASE1_OPERATIONS) == 23
    assert _phase1_operations(client.app) == PHASE1_OPERATIONS


def test_each_phase1_handler_resolves_and_opens_services_exactly_once() -> None:
    route_root = Path(__file__).parents[1] / "src" / "novel_api" / "routes"
    handlers: list[ast.FunctionDef] = []
    for name in ("work.py", "world.py", "timeline.py", "characters.py", "canon.py"):
        module = ast.parse((route_root / name).read_text(encoding="utf-8"))
        handlers.extend(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and any(isinstance(item, ast.Call) for item in node.decorator_list)
        )

    assert len(handlers) == 23
    for handler in handlers:
        calls = [
            node.func.id
            for node in ast.walk(handler)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert calls.count("resolve_project_target") == 1, handler.name
        assert calls.count("open_project_services") == 1, handler.name


def test_phase1_complete_http_workflow(client: TestClient) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-one"

    work = _data(client.get(f"{base}/work"))
    work = _data(
        client.patch(
            f"{base}/work",
            json={
                "working_title": "第一部 改訂",
                "expected_version": work["version"],
                "genre": "SF",
                "themes_json": {"themes": ["記憶"]},
                "production_status": "outlined",
            },
        )
    )
    assert work["working_title"] == "第一部 改訂"
    assert work["themes_json"] == '{"themes":["記憶"]}'

    fact = _data(
        client.post(
            f"{base}/world-facts",
            json={
                "statement": "火山異常を観測",
                "title": "火山異常",
                "details_json": {"severity": 3},
                "valid_from": "2126-01-01",
                "importance": 2,
            },
        )
    )
    assert fact["details_json"] == '{"severity":3}'
    found_facts = _data(
        client.get(f"{base}/world-facts/search", params={"query": "火山", "limit": 20})
    )
    assert [item["id"] for item in found_facts] == [fact["id"]]
    assert (
        _data(client.get(f"{base}/world-facts/{fact['id']}"))["statement"]
        == fact["statement"]
    )
    fact = _data(
        client.patch(
            f"{base}/world-facts/{fact['id']}",
            json={
                "statement": "火山異常は収束",
                "expected_version": fact["version"],
                "details_json": {"severity": 1},
            },
        )
    )

    character = _data(
        client.post(
            f"{base}/characters",
            json={
                "display_name": "冬子",
                "description": "火山研究者",
                "profile_json": {"language": "日本語"},
            },
        )
    )
    partner = _data(client.post(f"{base}/characters", json={"display_name": "春人"}))
    event = _data(
        client.post(
            f"{base}/timeline/events",
            json={
                "title": "火山会議",
                "event_date": "2126年春頃",
                "participants": [{"character_id": character["id"], "role": "報告者"}],
                "location_world_fact_id": fact["id"],
                "importance": 4,
            },
        )
    )
    other_event = _data(
        client.post(
            f"{base}/timeline/events",
            json={"title": "避難完了", "event_date": "2126-06-01"},
        )
    )
    found_events = _data(
        client.get(
            f"{base}/timeline/events/search", params={"query": "火山", "limit": 20}
        )
    )
    assert [item["id"] for item in found_events] == [event["id"]]
    assert _data(client.get(f"{base}/timeline/events/{event['id']}"))["title"] == (
        "火山会議"
    )
    event = _data(
        client.patch(
            f"{base}/timeline/events/{event['id']}",
            json={
                "expected_version": event["version"],
                "title": "火山対策会議",
                "participants": [{"character_id": character["id"], "role": "議長"}],
            },
        )
    )
    ranged = _data(
        client.get(
            f"{base}/timeline/range",
            params={"start": "2126-01-01", "end": "2126-12-31", "limit": 20},
        )
    )
    assert {item["id"] for item in ranged} == {event["id"], other_event["id"]}
    event = _data(
        client.post(
            f"{base}/timeline/events/{event['id']}/move",
            json={
                "expected_version": event["version"],
                "new_date": "2126-04-15",
            },
        )
    )
    relation = _data(
        client.post(
            f"{base}/timeline/relations",
            json={
                "source_id": event["id"],
                "target_id": other_event["id"],
                "relation_type": "causes",
            },
        )
    )
    assert relation["source_event_id"] == event["id"]

    found_characters = _data(
        client.get(f"{base}/characters/search", params={"query": "研究者"})
    )
    assert [item["id"] for item in found_characters] == [character["id"]]
    assert (
        _data(client.get(f"{base}/characters/{character['id']}"))["display_name"]
        == "冬子"
    )
    character = _data(
        client.patch(
            f"{base}/characters/{character['id']}",
            json={
                "expected_version": character["version"],
                "display_name": "冬子博士",
                "profile_json": {"language": "日本語", "rank": 1},
            },
        )
    )
    relationship = _data(
        client.post(
            f"{base}/relationships",
            json={
                "source_character_id": character["id"],
                "target_character_id": partner["id"],
                "relationship_type": "colleague",
                "description": "共同研究者",
            },
        )
    )
    relationship = _data(
        client.patch(
            f"{base}/relationships/{relationship['id']}",
            json={
                "expected_version": relationship["version"],
                "relationship_type": "friend",
                "description": "旧友",
            },
        )
    )
    relationships = _data(
        client.get(
            f"{base}/relationships",
            params={"character_id": character["id"], "limit": 20},
        )
    )
    assert [item["id"] for item in relationships] == [relationship["id"]]

    decision = _data(
        client.post(
            f"{base}/canon/status",
            json={
                "entity_type": "world_fact",
                "entity_id": fact["id"],
                "target_status": "canon",
                "expected_version": fact["version"],
                "reason": "物語の前提として確定",
            },
        )
    )
    decisions = _data(
        client.get(
            f"{base}/canon/decisions/search",
            params={"query": "world_fact", "limit": 20},
        )
    )
    assert [item["id"] for item in decisions] == [decision["id"]]
    assert _data(client.get(f"{base}/canon/decisions/{decision['id']}")) == decision


def test_phase1_stale_updates_include_safe_current_snapshot(client: TestClient) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-one"
    work = _data(client.get(f"{base}/work"))
    updated = _data(
        client.patch(
            f"{base}/work",
            json={
                "working_title": "new title",
                "expected_version": work["version"],
            },
        )
    )

    response = client.patch(
        f"{base}/work",
        json={"working_title": "stale", "expected_version": work["version"]},
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "VERSION_CONFLICT"
    assert error["project_id"] == "phase-one"
    assert error["details"] == {
        "entity_type": "work",
        "entity_id": updated["id"],
        "expected_version": work["version"],
        "current_version": updated["version"],
        "current_resource": updated,
        "domain_code": "VersionConflictError",
    }
    assert "sqlite" not in response.text.lower()


def test_phase1_entity_stale_updates_include_current_snapshot(
    client: TestClient,
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-one"
    first = _data(client.post(f"{base}/characters", json={"display_name": "甲"}))
    second = _data(client.post(f"{base}/characters", json={"display_name": "乙"}))
    resources = [
        (
            "world_fact",
            _data(client.post(f"{base}/world-facts", json={"statement": "旧設定"})),
            lambda item: (
                f"{base}/world-facts/{item['id']}",
                {"statement": "新設定", "expected_version": item["version"]},
            ),
        ),
        (
            "timeline_event",
            _data(client.post(f"{base}/timeline/events", json={"title": "旧事件"})),
            lambda item: (
                f"{base}/timeline/events/{item['id']}",
                {"title": "新事件", "expected_version": item["version"]},
            ),
        ),
        (
            "character",
            first,
            lambda item: (
                f"{base}/characters/{item['id']}",
                {"display_name": "甲改", "expected_version": item["version"]},
            ),
        ),
    ]
    relationship = _data(
        client.post(
            f"{base}/relationships",
            json={
                "source_character_id": first["id"],
                "target_character_id": second["id"],
                "relationship_type": "ally",
            },
        )
    )
    resources.append(
        (
            "relationship",
            relationship,
            lambda item: (
                f"{base}/relationships/{item['id']}",
                {
                    "relationship_type": "friend",
                    "expected_version": item["version"],
                },
            ),
        )
    )

    for entity_type, original, update_request in resources:
        path, payload = update_request(original)
        current = _data(client.patch(path, json=payload))
        stale = client.patch(path, json=payload)
        assert stale.status_code == 409
        details = stale.json()["error"]["details"]
        assert details["entity_type"] == entity_type
        assert details["entity_id"] == original["id"]
        assert details["expected_version"] == original["version"]
        assert details["current_version"] == current["version"]
        assert details["current_resource"] == current
        assert details["domain_code"] == "VersionConflictError"


def test_phase1_relationship_validation_and_canon_policy(client: TestClient) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-one"
    character = _data(client.post(f"{base}/characters", json={"display_name": "一人"}))
    self_relation = client.post(
        f"{base}/relationships",
        json={
            "source_character_id": character["id"],
            "target_character_id": character["id"],
            "relationship_type": "self",
        },
    )
    assert self_relation.status_code == 400
    assert self_relation.json()["error"]["code"] == "VALIDATION_ERROR"

    fact = _data(client.post(f"{base}/world-facts", json={"statement": "未確定設定"}))
    missing_reason = client.post(
        f"{base}/canon/status",
        json={
            "entity_type": "world_fact",
            "entity_id": fact["id"],
            "target_status": "canon",
            "expected_version": fact["version"],
        },
    )
    assert missing_reason.status_code == 409
    assert missing_reason.json()["error"] == {
        "code": "DEPENDENCY_CONFLICT",
        "message": "The request conflicts with related resources.",
        "project_id": "phase-one",
        "details": {"domain_code": "CANON_REASON_REQUIRED"},
    }


def test_phase1_cross_project_isolation(client: TestClient) -> None:
    _create_project(client, "project-a")
    _create_project(client, "project-b")
    fact = _data(
        client.post(
            "/api/v1/projects/project-a/world-facts",
            json={"statement": "Aだけの設定"},
        ),
        "project-a",
    )

    search_b = _data(
        client.get(
            "/api/v1/projects/project-b/world-facts/search",
            params={"query": "Aだけ"},
        ),
        "project-b",
    )
    get_b = client.get(f"/api/v1/projects/project-b/world-facts/{fact['id']}")

    assert search_b == []
    assert get_b.status_code == 404
    assert get_b.json()["error"]["code"] == "NOT_FOUND"


def test_public_world_fact_search_uses_search_service_and_supports_write(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-one"
    fact = _data(
        client.post(f"{base}/world-facts", json={"statement": "検索対象の設定"})
    )
    calls: list[tuple[str, int]] = []
    original = SearchService.search_world_facts

    def search(self: SearchService, query: str, limit: int):
        calls.append((query, limit))
        return original(self, query, limit)

    monkeypatch.setattr(SearchService, "search_world_facts", search)
    found = _data(
        client.get(f"{base}/world-facts/search", params={"query": "検索", "limit": 20})
    )

    assert [item["id"] for item in found] == [fact["id"]]
    assert calls == [("検索", 20)]
    updated = _data(
        client.patch(
            f"{base}/world-facts/{fact['id']}",
            json={"statement": "検索対象を更新", "expected_version": fact["version"]},
        )
    )
    assert updated["statement"] == "検索対象を更新"


def test_public_character_search_uses_search_service_and_supports_write(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-one"
    character = _data(
        client.post(f"{base}/characters", json={"display_name": "検索研究者"})
    )
    calls: list[tuple[str, int]] = []
    original = SearchService.search_characters

    def search(self: SearchService, query: str, limit: int):
        calls.append((query, limit))
        return original(self, query, limit)

    monkeypatch.setattr(SearchService, "search_characters", search)
    found = _data(
        client.get(f"{base}/characters/search", params={"query": "検索", "limit": 20})
    )

    assert [item["id"] for item in found] == [character["id"]]
    assert calls == [("検索", 20)]
    updated = _data(
        client.patch(
            f"{base}/characters/{character['id']}",
            json={
                "display_name": "検索研究者改",
                "expected_version": character["version"],
            },
        )
    )
    assert updated["display_name"] == "検索研究者改"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/timeline/relations",
            {"source_id": 1, "target_id": 1, "relation_type": "self"},
        ),
        (
            "post",
            "/canon/status",
            {
                "entity_type": "bad",
                "entity_id": 1,
                "target_status": "canon",
                "expected_version": 1,
            },
        ),
    ],
)
def test_phase1_invalid_domain_requests_use_common_contract(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> None:
    _create_project(client)
    request: Callable[..., Any] = getattr(client, method)
    response = request(f"/api/v1/projects/phase-one{path}", json=payload)
    assert response.status_code in (400, 404)
    assert response.json()["error"]["project_id"] == "phase-one"
