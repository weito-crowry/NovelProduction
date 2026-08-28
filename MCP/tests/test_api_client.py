from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from novel_mcp.api_client import (
    ApiClient,
    BackendProtocolError,
    BackendUnavailableError,
    RemoteApiError,
    project_success,
)
from novel_mcp.config import McpSettings, resolve_settings


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def test_resolve_settings_prefers_cli_then_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOVEL_API_URL", "http://environment:8765/")

    assert resolve_settings().api_url == "http://environment:8765"
    assert resolve_settings("http://cli:8765/").api_url == "http://cli:8765"


def test_request_json_forwards_path_query_and_body() -> None:
    async def exercise() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"value": "ok"})

        client = ApiClient(
            McpSettings("http://api.example/"),
            transport=httpx.MockTransport(handler),
        )
        try:
            assert await client.request_json(
                "POST",
                "/api/v1/projects/2126/work",
                params={"optional": "value"},
                json_body={"title": "作品"},
            ) == {"value": "ok"}
        finally:
            await client.aclose()

        assert requests[0].url == httpx.URL(
            "http://api.example/api/v1/projects/2126/work?optional=value"
        )
        assert requests[0].content == '{"title":"作品"}'.encode()

    _run(exercise())


def test_request_json_parses_api_error_without_leaking_transport_details() -> None:
    async def exercise() -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                409,
                json={
                    "error": {
                        "code": "VERSION_CONFLICT",
                        "message": "The resource was modified by another client.",
                        "project_id": "2126",
                        "details": {
                            "expected_version": 1,
                            "current_version": 2,
                            "current_resource": {"id": 4},
                        },
                    }
                },
            )

        client = ApiClient(
            McpSettings("http://api.example"),
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(RemoteApiError) as raised:
                await client.request_json("PATCH", "/api/v1/projects/2126/work")
        finally:
            await client.aclose()

        assert raised.value.code == "VERSION_CONFLICT"
        assert raised.value.project_id == "2126"
        assert raised.value.details["current_resource"] == {"id": 4}

    _run(exercise())


def test_request_json_maps_connection_failure_to_backend_unavailable() -> None:
    async def exercise() -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("secret socket detail")

        client = ApiClient(
            McpSettings("http://api.example"),
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(BackendUnavailableError) as raised:
                await client.request_json("GET", "/api/v1/health")
        finally:
            await client.aclose()

        assert "secret" not in str(raised.value)
        assert "socket" not in str(raised.value)

    _run(exercise())


def test_request_json_rejects_malformed_json() -> None:
    async def exercise() -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not-json")

        client = ApiClient(
            McpSettings("http://api.example"),
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(BackendProtocolError):
                await client.request_json("GET", "/api/v1/health")
        finally:
            await client.aclose()

    _run(exercise())


def test_project_envelope_rejects_mismatched_project_id() -> None:
    payload = {"project_id": "other", "data": {"id": 1}}

    with pytest.raises(BackendProtocolError):
        project_success(payload, "2126")


def test_project_success_unwraps_api_data_without_double_nesting() -> None:
    assert project_success(
        {"project_id": "2126", "data": {"id": 1}}, "2126"
    ) == {"ok": True, "project_id": "2126", "data": {"id": 1}}
