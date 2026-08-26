from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.types import CallToolResult

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.mcp_server import (
    ALL_TOOL_NAMES,
    PHASE1_TOOL_NAMES,
    PHASE2_TOOL_NAMES,
    PHASE3_TOOL_NAMES,
    create_server,
)

PHASE3_EXPECTED = {
    "episode_outline_get",
    "episode_context",
    "episode_draft_get",
    "episode_draft_save",
    "episode_draft_history",
}


def _config(tmp_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=tmp_path / "phase3" / "story.db",
        migration_dir=Path(__file__).resolve().parents[1] / "migrations",
    )


@pytest.fixture
def server(tmp_path: Path):
    value = create_server(_config(tmp_path))
    try:
        yield value
    finally:
        value.close()


def _payload(result: CallToolResult) -> dict[str, object]:
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def test_phase3_tool_inventory_is_exact(server) -> None:
    assert PHASE3_TOOL_NAMES == PHASE3_EXPECTED
    assert len(PHASE1_TOOL_NAMES) == 23
    assert len(PHASE2_TOOL_NAMES) == 27
    assert len(ALL_TOOL_NAMES) == 55
    assert server.tool_names() == ALL_TOOL_NAMES
    assert not server.tool_names() & {
        "continuity_check",
        "story_thread_get",
        "foreshadowing_graph_get",
    }


def test_phase3_annotations_descriptions_and_schema_bounds(server) -> None:
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == ALL_TOOL_NAMES
    for name in PHASE3_EXPECTED:
        tool = tools[name]
        assert tool.description.startswith("Use this when")
        assert tool.annotations is not None
        assert tool.annotations.open_world_hint is False

    for name in {
        "episode_outline_get",
        "episode_context",
        "episode_draft_get",
        "episode_draft_history",
    }:
        assert tools[name].annotations.read_only_hint is True
        assert tools[name].annotations.destructive_hint is False
    assert tools["episode_draft_save"].annotations.read_only_hint is False
    assert tools["episode_draft_save"].annotations.destructive_hint is False

    save_schema = tools["episode_draft_save"].input_schema["properties"]
    assert save_schema["body"]["minLength"] == 1
    assert save_schema["source_agent"]["anyOf"][0]["maxLength"] == 120
    assert save_schema["change_summary"]["maxLength"] == 1000
    history_schema = tools["episode_draft_history"].input_schema["properties"]
    assert history_schema["limit"]["minimum"] == 1
    assert history_schema["limit"]["maximum"] == 100


def test_phase3_draft_tools_preserve_body_and_return_metadata_only(
    server, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 3")
    chapter = _payload(
        asyncio.run(server.call_tool("chapter_create", {"title": "章"}))
    )["data"]
    episode = _payload(
        asyncio.run(
            server.call_tool(
                "episode_create", {"chapter_id": chapter["id"], "title": "話"}
            )
        )
    )["data"]

    body = "  本文\n\n"
    first = _payload(
        asyncio.run(
            server.call_tool(
                "episode_draft_save",
                {
                    "episode_id": episode["id"],
                    "body": body,
                    "source_agent": "Codex",
                    "change_summary": "初稿",
                },
            )
        )
    )
    assert first["ok"] is True
    first_draft = first["data"]
    second = _payload(
        asyncio.run(
            server.call_tool(
                "episode_draft_save",
                {
                    "episode_id": episode["id"],
                    "body": "第二稿",
                    "expected_parent_draft_id": first_draft["id"],
                },
            )
        )
    )
    assert second["data"]["revision"] == 2

    latest = _payload(
        asyncio.run(
            server.call_tool("episode_draft_get", {"episode_id": episode["id"]})
        )
    )
    assert latest["data"]["body"] == "第二稿"
    history = _payload(
        asyncio.run(
            server.call_tool("episode_draft_history", {"episode_id": episode["id"]})
        )
    )
    assert [item["revision"] for item in history["data"]] == [1, 2]
    assert all("body" not in item for item in history["data"])
