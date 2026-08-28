from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

PHASE2_OPERATIONS = {
    ("POST", "/api/v1/projects/{project_id}/chapters"),
    ("GET", "/api/v1/projects/{project_id}/chapters"),
    ("PATCH", "/api/v1/projects/{project_id}/chapters/{chapter_id}"),
    ("POST", "/api/v1/projects/{project_id}/chapters/{chapter_id}/reorder"),
    ("POST", "/api/v1/projects/{project_id}/chapters/{chapter_id}/episodes"),
    ("GET", "/api/v1/projects/{project_id}/chapters/{chapter_id}/episodes"),
    ("GET", "/api/v1/projects/{project_id}/episodes/{episode_id}"),
    ("PATCH", "/api/v1/projects/{project_id}/episodes/{episode_id}"),
    ("POST", "/api/v1/projects/{project_id}/episodes/{episode_id}/reorder"),
    ("POST", "/api/v1/projects/{project_id}/episodes/{episode_id}/scenes"),
    ("GET", "/api/v1/projects/{project_id}/episodes/{episode_id}/scenes"),
    ("GET", "/api/v1/projects/{project_id}/scenes/{scene_id}"),
    ("PATCH", "/api/v1/projects/{project_id}/scenes/{scene_id}"),
    ("POST", "/api/v1/projects/{project_id}/scenes/{scene_id}/reorder"),
    ("POST", "/api/v1/projects/{project_id}/episodes/{episode_id}/references"),
    (
        "DELETE",
        "/api/v1/projects/{project_id}/episodes/{episode_id}/references/"
        "{reference_type}/{target_id}",
    ),
    ("GET", "/api/v1/projects/{project_id}/episodes/{episode_id}/references"),
    (
        "PUT",
        "/api/v1/projects/{project_id}/characters/{character_id}/states/{episode_id}",
    ),
    (
        "GET",
        "/api/v1/projects/{project_id}/characters/{character_id}/states/{episode_id}",
    ),
    ("GET", "/api/v1/projects/{project_id}/characters/{character_id}/states"),
    ("POST", "/api/v1/projects/{project_id}/information"),
    ("GET", "/api/v1/projects/{project_id}/information/search"),
    (
        "GET",
        "/api/v1/projects/{project_id}/information/{information_item_id}",
    ),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/information/{information_item_id}",
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/information/{information_item_id}/"
        "reader-disclosure",
    ),
    (
        "PUT",
        "/api/v1/projects/{project_id}/characters/{character_id}/knowledge/"
        "{information_item_id}",
    ),
    (
        "GET",
        "/api/v1/projects/{project_id}/characters/{character_id}/knowledge",
    ),
}


def _phase2_operations(app: FastAPI) -> set[tuple[str, str]]:
    paths = app.openapi()["paths"]
    return {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if (method.upper(), path) in PHASE2_OPERATIONS
    }


def _data(response: Any, project_id: str = "phase-two") -> Any:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def _create_project(client: TestClient, project_id: str = "phase-two") -> None:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": "第二部"},
    )
    assert response.status_code == 201


def _create_character(client: TestClient, base: str, name: str = "冬子") -> Any:
    return _data(
        client.post(f"{base}/characters", json={"display_name": name}),
        base.rsplit("/", 1)[-1],
    )


def test_phase2_registers_exactly_all_27_operations(client: TestClient) -> None:
    assert len(PHASE2_OPERATIONS) == 27
    assert _phase2_operations(client.app) == PHASE2_OPERATIONS


def test_each_phase2_handler_resolves_and_opens_services_exactly_once() -> None:
    route_root = Path(__file__).parents[1] / "src" / "novel_api" / "routes"
    handlers: list[ast.FunctionDef] = []
    for name in ("narrative.py", "information.py"):
        module = ast.parse((route_root / name).read_text(encoding="utf-8"))
        handlers.extend(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and any(isinstance(item, ast.Call) for item in node.decorator_list)
        )

    assert len(handlers) == 27
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


def test_phase2_hierarchy_create_list_get_update_and_reorder(
    client: TestClient,
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-two"

    first_chapter = _data(
        client.post(
            f"{base}/chapters",
            json={
                "title": "第一章",
                "summary": "導入",
                "purpose": "出会い",
                "production_status": "outlined",
                "canon_status": "idea",
            },
        )
    )
    second_chapter = _data(client.post(f"{base}/chapters", json={"title": "第二章"}))
    assert (first_chapter["position"], second_chapter["position"]) == (1, 2)
    assert first_chapter["production_status"] == "outlined"
    chapters = _data(client.get(f"{base}/chapters"))
    assert [chapter["id"] for chapter in chapters] == [
        first_chapter["id"],
        second_chapter["id"],
    ]

    first_chapter = _data(
        client.patch(
            f"{base}/chapters/{first_chapter['id']}",
            json={
                "expected_version": first_chapter["version"],
                "title": "第一章 改稿",
                "summary": "改稿済み",
            },
        )
    )
    reordered_chapters = _data(
        client.post(
            f"{base}/chapters/{second_chapter['id']}/reorder",
            json={
                "target_position": 1,
                "expected_version": second_chapter["version"],
            },
        )
    )
    assert [chapter["id"] for chapter in reordered_chapters] == [
        second_chapter["id"],
        first_chapter["id"],
    ]

    first_episode = _data(
        client.post(
            f"{base}/chapters/{first_chapter['id']}/episodes",
            json={
                "title": "第一話",
                "summary": "目覚め",
                "purpose": "発端",
                "foreshadowing_notes": ["赤い光"],
                "production_status": "drafting",
            },
        )
    )
    second_episode = _data(
        client.post(
            f"{base}/chapters/{first_chapter['id']}/episodes",
            json={"title": "第二話"},
        )
    )
    assert first_episode["foreshadowing_notes_json"] == '["赤い光"]'
    assert _data(client.get(f"{base}/episodes/{first_episode['id']}")) == first_episode
    episodes = _data(client.get(f"{base}/chapters/{first_chapter['id']}/episodes"))
    assert [episode["id"] for episode in episodes] == [
        first_episode["id"],
        second_episode["id"],
    ]
    first_episode = _data(
        client.patch(
            f"{base}/episodes/{first_episode['id']}",
            json={
                "expected_version": first_episode["version"],
                "title": "第一話 改稿",
                "foreshadowing_notes": ["青い光"],
            },
        )
    )
    reordered_episodes = _data(
        client.post(
            f"{base}/episodes/{second_episode['id']}/reorder",
            json={
                "target_position": 1,
                "expected_version": second_episode["version"],
            },
        )
    )
    assert [episode["id"] for episode in reordered_episodes] == [
        second_episode["id"],
        first_episode["id"],
    ]

    first_scene = _data(
        client.post(
            f"{base}/episodes/{first_episode['id']}/scenes",
            json={"title": "到着", "purpose": "登場"},
        )
    )
    second_scene = _data(
        client.post(
            f"{base}/episodes/{first_episode['id']}/scenes",
            json={"title": "対話"},
        )
    )
    assert _data(client.get(f"{base}/scenes/{first_scene['id']}")) == first_scene
    scenes = _data(client.get(f"{base}/episodes/{first_episode['id']}/scenes"))
    assert [scene["id"] for scene in scenes] == [
        first_scene["id"],
        second_scene["id"],
    ]
    first_scene = _data(
        client.patch(
            f"{base}/scenes/{first_scene['id']}",
            json={
                "expected_version": first_scene["version"],
                "title": "到着 改稿",
                "production_status": "revising",
            },
        )
    )
    reordered_scenes = _data(
        client.post(
            f"{base}/scenes/{second_scene['id']}/reorder",
            json={
                "target_position": 1,
                "expected_version": second_scene["version"],
            },
        )
    )
    assert [scene["id"] for scene in reordered_scenes] == [
        second_scene["id"],
        first_scene["id"],
    ]


def test_phase2_references_states_information_disclosure_and_knowledge(
    client: TestClient,
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-two"
    character = _create_character(client, base)
    chapter = _data(client.post(f"{base}/chapters", json={"title": "章"}))
    episodes = [
        _data(
            client.post(
                f"{base}/chapters/{chapter['id']}/episodes",
                json={"title": f"第{index}話"},
            )
        )
        for index in (1, 2, 3)
    ]
    item = _data(
        client.post(
            f"{base}/information",
            json={
                "statement": "成功率100%_の秘密",
                "truth_status": "false",
                "authoring_guard": "主人公はまだ知らない",
                "notes_json": {"source": "draft"},
                "importance": 2,
            },
        )
    )
    assert item["notes_json"] == '{"source":"draft"}'
    found = _data(
        client.get(f"{base}/information/search", params={"query": "100%_", "limit": 20})
    )
    assert [row["id"] for row in found] == [item["id"]]
    assert _data(client.get(f"{base}/information/{item['id']}")) == item
    item = _data(
        client.patch(
            f"{base}/information/{item['id']}",
            json={
                "expected_version": item["version"],
                "statement": "成功率100%_の偽情報",
                "notes_json": {"source": "revision"},
            },
        )
    )

    reference = _data(
        client.post(
            f"{base}/episodes/{episodes[0]['id']}/references",
            json={"reference_type": "information", "target_id": item["id"]},
        )
    )
    assert reference["reference_type"] == "information"
    references = _data(
        client.get(
            f"{base}/episodes/{episodes[0]['id']}/references",
            params={"reference_type": "information"},
        )
    )
    assert [row["id"] for row in references] == [reference["id"]]
    removed = _data(
        client.delete(
            f"{base}/episodes/{episodes[0]['id']}/references/information/{item['id']}"
        )
    )
    assert removed is True
    assert _data(client.get(f"{base}/episodes/{episodes[0]['id']}/references")) == []

    first_state = _data(
        client.put(
            f"{base}/characters/{character['id']}/states/{episodes[0]['id']}",
            json={
                "physical_state": "healthy",
                "beliefs_json": {"city": "safe"},
                "state_json": {"mood": 1},
            },
        )
    )
    second_state = _data(
        client.put(
            f"{base}/characters/{character['id']}/states/{episodes[1]['id']}",
            json={"physical_state": "injured", "emotional_state": "動揺"},
        )
    )
    effective = _data(
        client.get(f"{base}/characters/{character['id']}/states/{episodes[2]['id']}")
    )
    assert effective["id"] == second_state["id"]
    history = _data(client.get(f"{base}/characters/{character['id']}/states"))
    assert [row["id"] for row in history] == [first_state["id"], second_state["id"]]

    disclosure = _data(
        client.put(
            f"{base}/information/{item['id']}/reader-disclosure",
            json={"episode_id": episodes[1]["id"]},
        )
    )
    assert disclosure["episode_id"] == episodes[1]["id"]
    event = _data(
        client.put(
            f"{base}/characters/{character['id']}/knowledge/{item['id']}",
            json={
                "episode_id": episodes[1]["id"],
                "knowledge_state": "believes",
                "note": "噂を信じた",
            },
        )
    )
    assert event["knowledge_state"] == "believes"
    effective_knowledge = _data(
        client.get(
            f"{base}/characters/{character['id']}/knowledge",
            params={"episode_id": episodes[2]["id"]},
        )
    )
    assert effective_knowledge[0]["event_id"] == event["id"]
    assert effective_knowledge[0]["information_item"]["id"] == item["id"]


def test_phase2_stale_narrative_writes_include_safe_current_snapshots(
    client: TestClient,
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-two"
    chapter = _data(client.post(f"{base}/chapters", json={"title": "章"}))
    current = _data(
        client.patch(
            f"{base}/chapters/{chapter['id']}",
            json={"expected_version": chapter["version"], "title": "改稿"},
        )
    )

    stale_update = client.patch(
        f"{base}/chapters/{chapter['id']}",
        json={"expected_version": chapter["version"], "title": "古い改稿"},
    )
    stale_reorder = client.post(
        f"{base}/chapters/{chapter['id']}/reorder",
        json={"target_position": 1, "expected_version": chapter["version"]},
    )

    for response in (stale_update, stale_reorder):
        assert response.status_code == 409
        details = response.json()["error"]["details"]
        assert details == {
            "entity_type": "chapter",
            "entity_id": chapter["id"],
            "expected_version": chapter["version"],
            "current_version": current["version"],
            "current_resource": current,
            "domain_code": "VersionConflictError",
        }
        assert "sqlite" not in response.text.lower()


def test_canon_status_stale_conflicts_include_narrative_and_information_snapshots(
    client: TestClient,
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-two"
    chapter = _data(client.post(f"{base}/chapters", json={"title": "章"}))
    current_chapter = _data(
        client.patch(
            f"{base}/chapters/{chapter['id']}",
            json={"expected_version": chapter["version"], "title": "改稿"},
        )
    )
    information_item = _data(
        client.post(f"{base}/information", json={"statement": "情報"})
    )
    current_information_item = _data(
        client.patch(
            f"{base}/information/{information_item['id']}",
            json={
                "expected_version": information_item["version"],
                "statement": "改稿情報",
            },
        )
    )

    for entity_type, entity, current in (
        ("chapter", chapter, current_chapter),
        ("information_item", information_item, current_information_item),
    ):
        stale = client.post(
            f"{base}/canon/status",
            json={
                "entity_type": entity_type,
                "entity_id": entity["id"],
                "target_status": "canon",
                "expected_version": entity["version"],
                "reason": "古い版からの確定",
            },
        )

        assert stale.status_code == 409
        details = stale.json()["error"]["details"]
        assert details == {
            "entity_type": entity_type,
            "entity_id": entity["id"],
            "expected_version": entity["version"],
            "current_version": current["version"],
            "current_resource": current,
            "domain_code": "VersionConflictError",
        }
        assert "sqlite" not in stale.text.lower()


def test_phase2_cross_project_ids_are_not_read_or_written(
    client: TestClient,
) -> None:
    _create_project(client, "project-a")
    _create_project(client, "project-b")
    base_a = "/api/v1/projects/project-a"
    base_b = "/api/v1/projects/project-b"
    chapter_a = _data(
        client.post(f"{base_a}/chapters", json={"title": "A章"}), "project-a"
    )
    episode_a = _data(
        client.post(
            f"{base_a}/chapters/{chapter_a['id']}/episodes",
            json={"title": "A話"},
        ),
        "project-a",
    )
    item_a = _data(
        client.post(f"{base_a}/information", json={"statement": "A情報"}),
        "project-a",
    )

    missing_episode = client.get(f"{base_b}/episodes/{episode_a['id']}")
    foreign_parent = client.post(
        f"{base_b}/chapters/{chapter_a['id']}/episodes", json={"title": "侵入"}
    )
    missing_information = client.get(f"{base_b}/information/{item_a['id']}")

    for response in (missing_episode, foreign_parent, missing_information):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


def test_phase2_deprecated_content_remains_visible_but_cannot_be_edited_or_leak(
    client: TestClient,
) -> None:
    _create_project(client)
    base = "/api/v1/projects/phase-two"
    character = _create_character(client, base)
    chapter = _data(client.post(f"{base}/chapters", json={"title": "撤回章"}))
    episode = _data(
        client.post(f"{base}/chapters/{chapter['id']}/episodes", json={"title": "話"})
    )
    item = _data(client.post(f"{base}/information", json={"statement": "撤回情報"}))
    _data(
        client.put(
            f"{base}/characters/{character['id']}/knowledge/{item['id']}",
            json={"episode_id": episode["id"], "knowledge_state": "knows"},
        )
    )

    for entity_type, entity in (("chapter", chapter), ("information_item", item)):
        canonical = _data(
            client.post(
                f"{base}/canon/status",
                json={
                    "entity_type": entity_type,
                    "entity_id": entity["id"],
                    "target_status": "canon",
                    "expected_version": entity["version"],
                    "reason": "採用",
                },
            )
        )
        _data(
            client.post(
                f"{base}/canon/status",
                json={
                    "entity_type": entity_type,
                    "entity_id": entity["id"],
                    "target_status": "deprecated",
                    "expected_version": canonical["changes"][0]["after_payload"][
                        "version"
                    ],
                    "reason": "撤回",
                },
            )
        )

    chapter_edit = client.patch(
        f"{base}/chapters/{chapter['id']}",
        json={"expected_version": 3, "title": "復活"},
    )
    information_edit = client.patch(
        f"{base}/information/{item['id']}",
        json={"expected_version": 3, "statement": "復活情報"},
    )
    for response in (chapter_edit, information_edit):
        assert response.status_code == 409
        assert response.json()["error"]["details"]["domain_code"] == (
            "CANON_POLICY_ERROR"
        )

    visible = _data(client.get(f"{base}/information/{item['id']}"))
    search = _data(
        client.get(f"{base}/information/search", params={"query": "撤回情報"})
    )
    knowledge = _data(
        client.get(
            f"{base}/characters/{character['id']}/knowledge",
            params={"episode_id": episode["id"]},
        )
    )
    assert visible["canon_status"] == "deprecated"
    assert [row["id"] for row in search] == [item["id"]]
    assert knowledge == []
