from __future__ import annotations

import asyncio
from typing import Any

import httpx

from novel_mcp.api_client import ApiClient
from novel_mcp.config import McpSettings
from novel_mcp.phase3_tools import register_phase3_tools


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def test_all_phase3_tools_map_to_the_canonical_http_routes() -> None:
    cases = {
        "episode_outline_get": (
            "GET",
            "episodes/1/outline",
            {"project_id": "p", "episode_id": 1},
        ),
        "episode_context": (
            "GET",
            "episodes/1/context",
            {"project_id": "p", "episode_id": 1},
        ),
        "episode_draft_get": (
            "GET",
            "episodes/1/draft",
            {"project_id": "p", "episode_id": 1},
        ),
        "episode_draft_save": (
            "POST",
            "episodes/1/drafts",
            {"project_id": "p", "episode_id": 1, "plain_text": "本文"},
        ),
        "episode_draft_history": (
            "GET",
            "episodes/1/drafts",
            {"project_id": "p", "episode_id": 1},
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
    register_phase3_tools(
        client, lambda name, handler, **_: registrations.update({name: handler})
    )
    try:
        for name, (method, suffix, arguments) in cases.items():
            result = _run(registrations[name](**arguments))
            assert result["ok"] is True, name
            assert requests[-1].method == method, name
            assert requests[-1].url.path == f"/api/v1/projects/p/{suffix}", name
    finally:
        _run(client.aclose())

    assert requests[2].url.params == httpx.QueryParams()
    assert requests[3].content == '{"plain_text":"本文","change_summary":""}'.encode()


def test_draft_save_forwards_parent_cas_fields_and_preserves_error_details() -> None:
    async def transport(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "VERSION_CONFLICT",
                    "message": "The resource was modified by another client.",
                    "project_id": "p",
                    "details": {
                        "expected_version": 4,
                        "current_version": 5,
                        "current_resource": {"id": 5},
                    },
                }
            },
        )

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    registrations: dict[str, Any] = {}
    register_phase3_tools(
        client, lambda name, handler, **_: registrations.update({name: handler})
    )
    try:
        result = _run(
            registrations["episode_draft_save"](
                project_id="p",
                episode_id=1,
                plain_text="本文",
                expected_parent_draft_id=4,
                source_agent="agent",
                change_summary="更新",
            )
        )
    finally:
        _run(client.aclose())

    assert result["error"]["details"]["current_resource"] == {"id": 5}


def test_draft_get_forwards_projection_and_repeated_annotation_keys() -> None:
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"project_id": "p", "data": {}})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    registrations: dict[str, Any] = {}
    register_phase3_tools(
        client, lambda name, handler, **_: registrations.update({name: handler})
    )
    try:
        _run(
            registrations["episode_draft_get"](
                project_id="p",
                episode_id=1,
                revision=4,
                format="html",
                annotation_projection="selected",
                annotation_keys=["emotions", "mood"],
                include_notes=True,
            )
        )
    finally:
        _run(client.aclose())

    assert requests[-1].url.params.multi_items() == [
        ("revision", "4"),
        ("annotation_projection", "selected"),
        ("annotation_keys", "emotions"),
        ("annotation_keys", "mood"),
        ("include_notes", "true"),
    ]
