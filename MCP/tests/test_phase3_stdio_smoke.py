from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

MCP_ROOT = Path(__file__).resolve().parents[1]


def _payload(result: CallToolResult) -> dict[str, Any]:
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def _run_stdio_smoke(base_url: str) -> str:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "novel_mcp.mcp_server", "--api-url", base_url],
        cwd=str(MCP_ROOT),
    )
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
        async with stdio_client(parameters, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 65
                by_name = {tool.name: tool for tool in tools.tools}
                assert "project_id" in by_name["work_get"].input_schema["required"]

                created = _payload(
                    await session.call_tool(
                        "project_create",
                        {"working_title": "stdio", "project_id": "stdio-project"},
                    )
                )
                assert created["ok"] is True
                listed = _payload(await session.call_tool("project_list", {}))
                assert listed["ok"] is True
                assert any(
                    item["project_id"] == "stdio-project"
                    for item in listed["data"]["projects"]
                )
                work = _payload(
                    await session.call_tool("work_get", {"project_id": "stdio-project"})
                )
                assert work["ok"] is True
                assert work["project_id"] == "stdio-project"

        errlog.seek(0)
        return errlog.read()


def test_phase3_stdio_smoke(api_url: str) -> None:
    errlog = asyncio.run(asyncio.wait_for(_run_stdio_smoke(api_url), timeout=45))
    assert "Traceback" not in errlog
