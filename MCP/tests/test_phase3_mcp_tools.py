from __future__ import annotations

import asyncio

import httpx

from novel_mcp.api_client import ApiClient
from novel_mcp.config import McpSettings
from novel_mcp.phase3_tools import register_phase3_tools


def test_phase3_tools_are_registered_as_http_handlers() -> None:
    async def transport(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"project_id": "p", "data": []})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    names: set[str] = set()
    register_phase3_tools(client, lambda name, _handler, **_: names.add(name))
    try:
        assert len(names) == 5
    finally:
        asyncio.run(client.aclose())
