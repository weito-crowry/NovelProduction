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

from novel_mcp.cli import initialize_work

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = PROJECT_ROOT / "migrations"


def _data(result: CallToolResult) -> Any:
    payload = result.structured_content
    assert payload is not None
    assert payload["ok"] is True
    return payload["data"]


async def _run_stdio_smoke(db_path: Path) -> str:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "novel_mcp.mcp_server",
            "--db",
            str(db_path),
            "--migration-dir",
            str(MIGRATIONS),
        ],
        cwd=PROJECT_ROOT,
    )

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
        async with stdio_client(parameters, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 55

                chapter = _data(
                    await session.call_tool("chapter_create", {"title": "章"})
                )
                previous = _data(
                    await session.call_tool(
                        "episode_create",
                        {"chapter_id": chapter["id"], "title": "前話"},
                    )
                )
                target = _data(
                    await session.call_tool(
                        "episode_create",
                        {"chapter_id": chapter["id"], "title": "対象話"},
                    )
                )
                future = _data(
                    await session.call_tool(
                        "episode_create",
                        {"chapter_id": chapter["id"], "title": "未来話"},
                    )
                )
                character = _data(
                    await session.call_tool(
                        "character_create", {"display_name": "主人公"}
                    )
                )
                _data(
                    await session.call_tool(
                        "episode_reference_add",
                        {
                            "episode_id": target["id"],
                            "reference_type": "character",
                            "target_id": character["id"],
                        },
                    )
                )
                _data(
                    await session.call_tool(
                        "character_state_set",
                        {
                            "character_id": character["id"],
                            "episode_id": previous["id"],
                            "physical_state": "stable",
                            "beliefs_json": {"stance": "resolved"},
                        },
                    )
                )

                current_reveal = _data(
                    await session.call_tool(
                        "information_create",
                        {
                            "statement": "CURRENT_REVEAL_SENTINEL",
                            "truth_status": "true",
                        },
                    )
                )
                _data(
                    await session.call_tool(
                        "reader_disclosure_set",
                        {
                            "information_item_id": current_reveal["id"],
                            "episode_id": target["id"],
                        },
                    )
                )

                protected = _data(
                    await session.call_tool(
                        "information_create",
                        {
                            "statement": "PROTECTED_FUTURE_SENTINEL",
                            "truth_status": "true",
                            "authoring_guard": "Keep the protected item undisclosed.",
                        },
                    )
                )
                _data(
                    await session.call_tool(
                        "reader_disclosure_set",
                        {
                            "information_item_id": protected["id"],
                            "episode_id": future["id"],
                        },
                    )
                )
                _data(
                    await session.call_tool(
                        "episode_reference_add",
                        {
                            "episode_id": target["id"],
                            "reference_type": "information",
                            "target_id": protected["id"],
                        },
                    )
                )

                first = _data(
                    await session.call_tool(
                        "episode_draft_save",
                        {"episode_id": target["id"], "body": "revision one"},
                    )
                )
                second = _data(
                    await session.call_tool(
                        "episode_draft_save",
                        {
                            "episode_id": target["id"],
                            "body": "revision two",
                            "expected_parent_draft_id": first["id"],
                        },
                    )
                )
                assert (first["revision"], second["revision"]) == (1, 2)

                context = _data(
                    await session.call_tool(
                        "episode_context", {"episode_id": target["id"]}
                    )
                )
                reveal_ids = {
                    item["id"]
                    for item in context["reader_context"]["reveal_this_episode"]
                }
                assert current_reveal["id"] in reveal_ids
                assert context["participants"][0]["effective_state"]["beliefs"] == {
                    "stance": "resolved"
                }
                serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)
                assert "PROTECTED_FUTURE_SENTINEL" not in serialized

                history = _data(
                    await session.call_tool(
                        "episode_draft_history", {"episode_id": target["id"]}
                    )
                )
                assert [item["revision"] for item in history] == [1, 2]

        errlog.seek(0)
        return errlog.read()


def test_phase3_stdio_smoke(tmp_path: Path) -> None:
    db_path = tmp_path / "stdio" / "story.db"
    initialize_work(db_path, "Phase 3 stdio smoke")

    errlog = asyncio.run(asyncio.wait_for(_run_stdio_smoke(db_path), timeout=30))

    assert "Traceback" not in errlog
