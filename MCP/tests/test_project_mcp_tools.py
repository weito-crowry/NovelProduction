from __future__ import annotations

import asyncio
from typing import Any

import httpx

from novel_mcp.api_client import ApiClient
from novel_mcp.project_tools import register_project_tools


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def _registered(client: ApiClient) -> tuple[dict[str, Any], dict[str, Any]]:
    registrations: dict[str, Any] = {}

    def register(name: str, handler: Any, **kwargs: Any) -> None:
        registrations[name] = {"handler": handler, **kwargs}

    register_project_tools(client, register)
    return registrations, {
        name: registrations[name]["handler"] for name in registrations
    }


def test_project_tools_register_exact_names_and_annotations() -> None:
    client = ApiClient(_settings(), transport=httpx.MockTransport(_response({})))
    try:
        registrations, _ = _registered(client)
    finally:
        _run(client.aclose())

    assert set(registrations) == {
        "project_list",
        "project_get",
        "project_create",
        "project_update",
    }
    assert registrations["project_list"]["read_only"] is True
    assert registrations["project_list"]["destructive"] is False
    assert registrations["project_get"]["read_only"] is True
    assert registrations["project_get"]["destructive"] is False
    assert registrations["project_create"]["read_only"] is False
    assert registrations["project_create"]["destructive"] is False
    assert registrations["project_update"]["read_only"] is False
    assert registrations["project_update"]["destructive"] is True


def test_project_tools_forward_paths_and_envelopes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/api/v1/projects":
            return httpx.Response(200, json={"projects": [{"project_id": "a"}]})
        project_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={"project_id": project_id, "status": "active"})

    client = ApiClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        registrations, handlers = _registered(client)
        assert _run(handlers["project_list"](include_archived=True)) == {
            "ok": True,
            "data": {"projects": [{"project_id": "a"}]},
        }
        assert _run(handlers["project_get"](project_id="a")) == {
            "ok": True,
            "project_id": "a",
            "data": {"project_id": "a", "status": "active"},
        }
        assert _run(handlers["project_create"](working_title="作品"))["ok"] is True
        assert _run(
            handlers["project_update"](project_id="a", status="archived")
        )["project_id"] == "a"
        assert registrations["project_get"]["handler"].__annotations__["project_id"]
    finally:
        _run(client.aclose())

    assert requests[0].url == httpx.URL(
        "http://api.example/api/v1/projects?include_archived=true"
    )
    assert requests[1].url.path == "/api/v1/projects/a"
    assert requests[2].content == '{"working_title":"作品"}'.encode()
    assert requests[3].method == "PATCH"
    assert requests[3].content == b'{"status":"archived"}'


def test_project_list_forwards_default_false_query() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"projects": []})

    client = ApiClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        _, handlers = _registered(client)
        _run(handlers["project_list"]())
    finally:
        _run(client.aclose())

    assert requests[0].url == httpx.URL(
        "http://api.example/api/v1/projects?include_archived=false"
    )


def test_project_tool_error_preserves_api_error_shape() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "PROJECT_CONFLICT",
                    "message": "The requested project already exists.",
                    "project_id": "a",
                    "details": {"reason": "exists"},
                }
            },
        )

    client = ApiClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        _, handlers = _registered(client)
        result = _run(handlers["project_get"](project_id="a"))
    finally:
        _run(client.aclose())

    assert result == {
        "ok": False,
        "error": {
            "code": "PROJECT_CONFLICT",
            "message": "The requested project already exists.",
            "project_id": "a",
            "details": {"reason": "exists"},
        },
    }


def _settings() -> Any:
    from novel_mcp.config import McpSettings

    return McpSettings("http://api.example")


def _response(payload: Any) -> Any:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler
