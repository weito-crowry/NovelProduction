from __future__ import annotations

import asyncio
from typing import Any

import httpx

from novel_mcp.api_client import ApiClient
from novel_mcp.config import McpSettings
from novel_mcp.style_analysis_tools import register_style_analysis_tools


def test_style_analysis_tools_register_exact_six_and_map_project_paths() -> None:
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"project_id": "p", "data": {}})

    client = ApiClient(
        McpSettings("http://api.example"), transport=httpx.MockTransport(transport)
    )
    handlers: dict[str, Any] = {}
    register_style_analysis_tools(
        client, lambda name, handler, **_: handlers.__setitem__(name, handler)
    )
    try:
        assert set(handlers) == {
            "style_analysis_catalog_get",
            "style_analysis_result_get",
            "style_analysis_external_start",
            "style_analysis_external_status",
            "style_analysis_external_submit",
            "style_analysis_external_cancel",
        }
        asyncio.run(
            handlers["style_analysis_external_start"](
                project_id="p",
                target={
                    "kind": "document",
                    "document_id": 1,
                    "text_revision_id": 2,
                },
                executor_model_id="gpt-test",
            )
        )
        assert requests[-1].url.path == (
            "/api/v1/projects/p/style-analysis/external-sessions"
        )
        assert requests[-1].method == "POST"
    finally:
        asyncio.run(client.aclose())
