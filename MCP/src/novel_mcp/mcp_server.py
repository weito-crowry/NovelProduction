from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from novel_mcp.api_client import ApiClient
from novel_mcp.config import McpSettings, resolve_settings
from novel_mcp.phase1_tools import register_phase1_tools
from novel_mcp.phase2_tool_descriptions import PHASE2_TOOL_DESCRIPTIONS
from novel_mcp.phase2_tools import register_phase2_tools
from novel_mcp.phase3_tool_descriptions import PHASE3_TOOL_DESCRIPTIONS
from novel_mcp.phase3_tools import register_phase3_tools
from novel_mcp.project_tool_descriptions import PROJECT_TOOL_DESCRIPTIONS
from novel_mcp.project_tools import register_project_tools
from novel_mcp.tool_descriptions import TOOL_DESCRIPTIONS
from novel_mcp.tool_support import Handler

PROJECT_TOOL_NAMES = frozenset(PROJECT_TOOL_DESCRIPTIONS)
PHASE1_TOOL_NAMES = frozenset(TOOL_DESCRIPTIONS)
PHASE2_TOOL_NAMES = frozenset(PHASE2_TOOL_DESCRIPTIONS)
PHASE3_TOOL_NAMES = frozenset(PHASE3_TOOL_DESCRIPTIONS)
ALL_TOOL_NAMES = (
    PROJECT_TOOL_NAMES | PHASE1_TOOL_NAMES | PHASE2_TOOL_NAMES | PHASE3_TOOL_NAMES
)


class NovelMCPServer(MCPServer):
    def __init__(self, *args: Any, api_client: ApiClient, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._api_client = api_client
        self._closed = False

    async def aclose(self) -> None:
        if not self._closed:
            await self._api_client.aclose()
            self._closed = True

    def tool_names(self) -> frozenset[str]:
        return frozenset(tool.name for tool in self._tool_manager.list_tools())


Registrar = Callable[..., None]


def create_server(
    settings: McpSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> NovelMCPServer:
    client = ApiClient(settings, transport=transport)
    server = NovelMCPServer("novel-production", version="0.1.0", api_client=client)
    descriptions = {
        **PROJECT_TOOL_DESCRIPTIONS,
        **TOOL_DESCRIPTIONS,
        **PHASE2_TOOL_DESCRIPTIONS,
        **PHASE3_TOOL_DESCRIPTIONS,
    }

    def register(
        name: str, handler: Handler, *, read_only: bool, destructive: bool
    ) -> None:
        server.add_tool(
            handler,
            name=name,
            description=descriptions[name],
            annotations=ToolAnnotations(
                read_only_hint=read_only,
                destructive_hint=destructive,
                open_world_hint=False,
            ),
            structured_output=True,
        )

    try:
        register_project_tools(client, register)
        register_phase1_tools(client, register)
        register_phase2_tools(client, register)
        register_phase3_tools(client, register)
    except Exception:
        asyncio.run(server.aclose())
        raise
    return server


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--api-url")
    return value


async def _run(server: NovelMCPServer) -> None:
    try:
        await server.run_stdio_async()
    finally:
        await server.aclose()


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    server = create_server(resolve_settings(args.api_url))
    asyncio.run(_run(server))


if __name__ == "__main__":
    main()
