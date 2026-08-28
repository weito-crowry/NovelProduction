from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from novel_mcp.api_client import ApiClient
from novel_mcp.config import McpSettings
from novel_mcp.phase1_tools import register_phase1_tools


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def test_all_phase1_tools_map_to_the_canonical_http_routes() -> None:
    cases = {
        "work_get": ("GET", "work", {"project_id": "p"}),
        "work_update": (
            "PATCH",
            "work",
            {"project_id": "p", "working_title": "x", "expected_version": 1},
        ),
        "world_fact_create": (
            "POST",
            "world-facts",
            {"project_id": "p", "statement": "x"},
        ),
        "world_fact_update": (
            "PATCH",
            "world-facts/1",
            {"project_id": "p", "fact_id": 1, "statement": "x", "expected_version": 1},
        ),
        "world_fact_get": ("GET", "world-facts/1", {"project_id": "p", "fact_id": 1}),
        "world_fact_search": (
            "GET",
            "world-facts/search",
            {"project_id": "p", "query": "検索"},
        ),
        "timeline_event_create": (
            "POST",
            "timeline/events",
            {"project_id": "p", "title": "x"},
        ),
        "timeline_event_update": (
            "PATCH",
            "timeline/events/1",
            {"project_id": "p", "event_id": 1, "expected_version": 1},
        ),
        "timeline_event_get": (
            "GET",
            "timeline/events/1",
            {"project_id": "p", "event_id": 1},
        ),
        "timeline_event_search": (
            "GET",
            "timeline/events/search",
            {"project_id": "p", "query": "検索"},
        ),
        "timeline_range": (
            "GET",
            "timeline/range",
            {"project_id": "p", "start": "2026-01-01", "end": "2026-01-02"},
        ),
        "timeline_move": (
            "POST",
            "timeline/events/1/move",
            {
                "project_id": "p",
                "event_id": 1,
                "expected_version": 1,
                "new_date": "2026-01-02",
            },
        ),
        "timeline_relation_create": (
            "POST",
            "timeline/relations",
            {
                "project_id": "p",
                "source_id": 1,
                "target_id": 2,
                "relation_type": "causes",
            },
        ),
        "character_create": (
            "POST",
            "characters",
            {"project_id": "p", "display_name": "x"},
        ),
        "character_update": (
            "PATCH",
            "characters/1",
            {"project_id": "p", "character_id": 1, "expected_version": 1},
        ),
        "character_get": (
            "GET",
            "characters/1",
            {"project_id": "p", "character_id": 1},
        ),
        "character_search": (
            "GET",
            "characters/search",
            {"project_id": "p", "query": "検索"},
        ),
        "relationship_create": (
            "POST",
            "relationships",
            {
                "project_id": "p",
                "source_character_id": 1,
                "target_character_id": 2,
                "relationship_type": "ally",
            },
        ),
        "relationship_update": (
            "PATCH",
            "relationships/1",
            {
                "project_id": "p",
                "relationship_id": 1,
                "expected_version": 1,
                "relationship_type": "ally",
            },
        ),
        "relationship_search": ("GET", "relationships", {"project_id": "p"}),
        "canon_status_set": (
            "POST",
            "canon/status",
            {
                "project_id": "p",
                "entity_type": "character",
                "entity_id": 1,
                "target_status": "canon",
                "expected_version": 1,
            },
        ),
        "canon_decision_get": (
            "GET",
            "canon/decisions/1",
            {"project_id": "p", "decision_id": 1},
        ),
        "canon_decision_search": (
            "GET",
            "canon/decisions/search",
            {"project_id": "p", "query": "検索"},
        ),
    }
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"project_id": "p", "data": {"ok": True}})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    registrations: dict[str, Any] = {}

    def register(name: str, handler: Any, **_: Any) -> None:
        registrations[name] = handler

    register_phase1_tools(client, register)
    try:
        for name, (method, suffix, arguments) in cases.items():
            result = _run(registrations[name](**arguments))
            assert result == {"ok": True, "project_id": "p", "data": {"ok": True}}
            request = requests[-1]
            assert request.method == method, name
            assert request.url.path == f"/api/v1/projects/p/{suffix}", name
    finally:
        _run(client.aclose())

    assert set(registrations) == set(cases)
    assert all(
        next(iter(__import__("inspect").signature(handler).parameters)) == "project_id"
        for handler in registrations.values()
    )


def test_phase1_optional_relationship_query_is_omitted_and_json_is_decoded() -> None:
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"project_id": "p", "data": {}})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    registrations: dict[str, Any] = {}
    register_phase1_tools(
        client, lambda name, handler, **_: registrations.update({name: handler})
    )
    try:
        assert _run(registrations["relationship_search"](project_id="p"))["ok"] is True
        assert "character_id" not in requests[-1].url.params
        _run(
            registrations["world_fact_create"](
                project_id="p", statement="設定", details_json='{"重要":true}'
            )
        )
        assert json.loads(requests[-1].content)["details_json"] == {"重要": True}
        invalid = _run(
            registrations["world_fact_create"](
                project_id="p", statement="設定", details_json="not-json"
            )
        )
    finally:
        _run(client.aclose())

    assert invalid["error"]["code"] == "VALIDATION_ERROR"
