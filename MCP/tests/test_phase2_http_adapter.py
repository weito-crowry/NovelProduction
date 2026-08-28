from __future__ import annotations

import asyncio
import inspect
from typing import Any

import httpx

from novel_mcp.api_client import ApiClient
from novel_mcp.config import McpSettings
from novel_mcp.phase2_tools import register_phase2_tools


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def test_all_phase2_tools_map_to_the_canonical_http_routes() -> None:
    cases = {
        "chapter_create": ("POST", "chapters", {"project_id": "p", "title": "x"}),
        "chapter_update": (
            "PATCH",
            "chapters/1",
            {"project_id": "p", "chapter_id": 1, "expected_version": 1},
        ),
        "chapter_reorder": (
            "POST",
            "chapters/1/reorder",
            {
                "project_id": "p",
                "chapter_id": 1,
                "target_position": 2,
                "expected_version": 1,
            },
        ),
        "chapter_list": ("GET", "chapters", {"project_id": "p"}),
        "episode_create": (
            "POST",
            "chapters/1/episodes",
            {"project_id": "p", "chapter_id": 1, "title": "x"},
        ),
        "episode_update": (
            "PATCH",
            "episodes/1",
            {"project_id": "p", "episode_id": 1, "expected_version": 1},
        ),
        "episode_get": ("GET", "episodes/1", {"project_id": "p", "episode_id": 1}),
        "episode_reorder": (
            "POST",
            "episodes/1/reorder",
            {
                "project_id": "p",
                "episode_id": 1,
                "target_position": 2,
                "expected_version": 1,
            },
        ),
        "episode_list": (
            "GET",
            "chapters/1/episodes",
            {"project_id": "p", "chapter_id": 1},
        ),
        "scene_create": (
            "POST",
            "episodes/1/scenes",
            {"project_id": "p", "episode_id": 1, "title": "x"},
        ),
        "scene_update": (
            "PATCH",
            "scenes/1",
            {"project_id": "p", "scene_id": 1, "expected_version": 1},
        ),
        "scene_get": ("GET", "scenes/1", {"project_id": "p", "scene_id": 1}),
        "scene_reorder": (
            "POST",
            "scenes/1/reorder",
            {
                "project_id": "p",
                "scene_id": 1,
                "target_position": 2,
                "expected_version": 1,
            },
        ),
        "scene_list": (
            "GET",
            "episodes/1/scenes",
            {"project_id": "p", "episode_id": 1},
        ),
        "episode_reference_add": (
            "POST",
            "episodes/1/references",
            {
                "project_id": "p",
                "episode_id": 1,
                "reference_type": "character",
                "target_id": 2,
            },
        ),
        "episode_reference_remove": (
            "DELETE",
            "episodes/1/references/character/2",
            {
                "project_id": "p",
                "episode_id": 1,
                "reference_type": "character",
                "target_id": 2,
            },
        ),
        "episode_reference_list": (
            "GET",
            "episodes/1/references",
            {"project_id": "p", "episode_id": 1},
        ),
        "character_state_set": (
            "PUT",
            "characters/1/states/2",
            {"project_id": "p", "character_id": 1, "episode_id": 2},
        ),
        "character_state_get": (
            "GET",
            "characters/1/states/2",
            {"project_id": "p", "character_id": 1, "episode_id": 2},
        ),
        "character_state_history": (
            "GET",
            "characters/1/states",
            {"project_id": "p", "character_id": 1},
        ),
        "information_create": (
            "POST",
            "information",
            {"project_id": "p", "statement": "x"},
        ),
        "information_update": (
            "PATCH",
            "information/1",
            {"project_id": "p", "information_item_id": 1, "expected_version": 1},
        ),
        "information_get": (
            "GET",
            "information/1",
            {"project_id": "p", "information_item_id": 1},
        ),
        "information_search": (
            "GET",
            "information/search",
            {"project_id": "p", "query": "x"},
        ),
        "reader_disclosure_set": (
            "PUT",
            "information/1/reader-disclosure",
            {"project_id": "p", "information_item_id": 1, "episode_id": 2},
        ),
        "character_knowledge_set": (
            "PUT",
            "characters/1/knowledge/2",
            {
                "project_id": "p",
                "character_id": 1,
                "information_item_id": 2,
                "episode_id": 3,
                "knowledge_state": "knows",
            },
        ),
        "character_knowledge_get": (
            "GET",
            "characters/1/knowledge",
            {"project_id": "p", "character_id": 1, "episode_id": 2},
        ),
    }
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"project_id": "p", "data": {}})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    registrations: dict[str, Any] = {}

    def register(name: str, handler: Any, **_: Any) -> None:
        registrations[name] = handler

    register_phase2_tools(client, register)
    try:
        for name, (method, suffix, arguments) in cases.items():
            result = _run(registrations[name](**arguments))
            assert result["ok"] is True, name
            assert requests[-1].method == method, name
            assert requests[-1].url.path == f"/api/v1/projects/p/{suffix}", name
    finally:
        _run(client.aclose())

    assert set(registrations) == set(cases)
    assert all(
        next(iter(inspect.signature(handler).parameters)) == "project_id"
        for handler in registrations.values()
    )


def test_phase2_delete_has_no_json_body_and_optional_reference_query_is_omitted() -> (
    None
):
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"project_id": "p", "data": {}})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    registrations: dict[str, Any] = {}
    register_phase2_tools(
        client, lambda name, handler, **_: registrations.update({name: handler})
    )
    try:
        _run(
            registrations["episode_reference_remove"](
                project_id="p", episode_id=1, reference_type="character", target_id=2
            )
        )
        assert requests[-1].content == b""
        _run(registrations["episode_reference_list"](project_id="p", episode_id=1))
    finally:
        _run(client.aclose())

    assert "reference_type" not in requests[-1].url.params


def test_phase2_json_like_inputs_decode_strings_and_reject_invalid_json() -> None:
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"project_id": "p", "data": {}})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    registrations: dict[str, Any] = {}
    register_phase2_tools(
        client, lambda name, handler, **_: registrations.update({name: handler})
    )
    try:
        result = _run(
            registrations["episode_create"](
                project_id="p", chapter_id=1, title="x", foreshadowing_notes='["clue"]'
            )
        )
        assert result["ok"] is True
        assert requests[-1].content == (
            b'{"title":"x","summary":"","purpose":"",'
            b'"foreshadowing_notes":["clue"],"production_status":"planned",'
            b'"canon_status":"draft"}'
        )

        result = _run(
            registrations["information_create"](
                project_id="p", statement="x", notes_json="not-json"
            )
        )
        assert result == {
            "ok": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "notes_json must contain valid JSON.",
                "project_id": "p",
                "details": {},
            },
        }
        assert len(requests) == 1
    finally:
        _run(client.aclose())
