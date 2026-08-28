from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from novel_mcp.config import McpSettings
from novel_mcp.mcp_server import (
    ALL_TOOL_NAMES,
    PHASE1_TOOL_NAMES,
    PHASE2_TOOL_NAMES,
    PHASE3_TOOL_NAMES,
    PROJECT_TOOL_NAMES,
    create_server,
    parser,
)


def _run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def test_http_server_owns_no_database_and_registers_59_tools() -> None:
    async def transport(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"project_id": "p", "data": {}})

    server = create_server(
        McpSettings("http://api.example"),
        transport=httpx.MockTransport(transport),
    )
    try:
        assert len(ALL_TOOL_NAMES) == 59
        assert len(PROJECT_TOOL_NAMES) == 4
        assert len(PHASE1_TOOL_NAMES) == 23
        assert len(PHASE2_TOOL_NAMES) == 27
        assert len(PHASE3_TOOL_NAMES) == 5
        assert "project_select" not in server.tool_names()
        tools = {tool.name: tool for tool in _run(server.list_tools())}
        assert set(tools) == ALL_TOOL_NAMES
        assert all(
            "project_id" in tools[name].input_schema.get("required", [])
            for name in ALL_TOOL_NAMES - {"project_list", "project_create"}
        )
        assert "project_id" not in tools["project_create"].input_schema.get(
            "required", []
        )
    finally:
        _run(server.aclose())


def test_server_cli_accepts_api_url_and_rejects_database_arguments() -> None:
    args = parser().parse_args(["--api-url", "http://cli:8765"])
    assert args.api_url == "http://cli:8765"

    with pytest.raises(SystemExit):
        parser().parse_args(["--db", "story.db"])
