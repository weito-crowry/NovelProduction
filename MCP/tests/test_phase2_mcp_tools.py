from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.types import CallToolResult

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.mcp_server import (
    PHASE1_TOOL_NAMES,
    PHASE2_TOOL_NAMES,
    create_server,
)

PHASE2_EXPECTED = {
    "chapter_create",
    "chapter_update",
    "chapter_reorder",
    "chapter_list",
    "episode_create",
    "episode_update",
    "episode_get",
    "episode_reorder",
    "episode_list",
    "scene_create",
    "scene_update",
    "scene_get",
    "scene_reorder",
    "scene_list",
    "episode_reference_add",
    "episode_reference_remove",
    "episode_reference_list",
    "character_state_set",
    "character_state_get",
    "character_state_history",
    "information_create",
    "information_update",
    "information_get",
    "information_search",
    "reader_disclosure_set",
    "character_knowledge_set",
    "character_knowledge_get",
}


def _config(tmp_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=tmp_path / "phase2" / "story.db",
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


def test_phase2_tool_inventory_is_exact_and_phase3_is_absent(server) -> None:
    assert PHASE2_TOOL_NAMES == PHASE2_EXPECTED
    assert server.tool_names() == PHASE1_TOOL_NAMES | PHASE2_EXPECTED
    assert not server.tool_names() & {
        "episode_outline_get",
        "episode_context",
        "episode_draft_get",
        "episode_draft_save",
        "episode_draft_history",
    }


def test_phase2_annotations_descriptions_and_schema_bounds(server) -> None:
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == PHASE1_TOOL_NAMES | PHASE2_EXPECTED
    for name in PHASE2_EXPECTED:
        tool = tools[name]
        assert tool.description
        assert tool.description.startswith("Use this when")
        assert tool.annotations is not None
        assert tool.annotations.open_world_hint is False

    assert tools["chapter_list"].annotations.read_only_hint is True
    assert tools["chapter_list"].annotations.destructive_hint is False
    assert tools["chapter_create"].annotations.read_only_hint is False
    assert tools["chapter_create"].annotations.destructive_hint is False
    assert tools["chapter_update"].annotations.read_only_hint is False
    assert tools["chapter_update"].annotations.destructive_hint is True
    assert tools["episode_reference_remove"].annotations.destructive_hint is True
    assert (
        tools["information_search"].input_schema["properties"]["limit"]["maximum"]
        == 100
    )
    assert tools["information_create"].input_schema["properties"]["truth_status"][
        "enum"
    ] == ["true", "false", "uncertain", "subjective"]
    assert tools["episode_reference_add"].input_schema["properties"]["reference_type"][
        "enum"
    ] == ["character", "world_fact", "timeline_event", "information"]


def test_phase2_tools_return_structured_narrative_and_state_data(
    server, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 2")

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
    scene = _payload(
        asyncio.run(
            server.call_tool(
                "scene_create", {"episode_id": episode["id"], "title": "場面"}
            )
        )
    )["data"]
    character = _payload(
        asyncio.run(server.call_tool("character_create", {"display_name": "主人公"}))
    )["data"]
    information = _payload(
        asyncio.run(
            server.call_tool(
                "information_create",
                {"statement": "偽の噂", "truth_status": "false"},
            )
        )
    )["data"]

    assert scene["episode_id"] == episode["id"]
    knowledge = _payload(
        asyncio.run(
            server.call_tool(
                "character_knowledge_set",
                {
                    "character_id": character["id"],
                    "information_item_id": information["id"],
                    "episode_id": episode["id"],
                    "knowledge_state": "believes",
                },
            )
        )
    )
    assert knowledge["ok"] is True
    effective = _payload(
        asyncio.run(
            server.call_tool(
                "character_knowledge_get",
                {"character_id": character["id"], "episode_id": episode["id"]},
            )
        )
    )
    assert effective["data"][0]["knowledge_state"] == "believes"
    assert effective["data"][0]["information_item"]["truth_status"] == "false"

    reference = _payload(
        asyncio.run(
            server.call_tool(
                "episode_reference_add",
                {
                    "episode_id": episode["id"],
                    "reference_type": "information",
                    "target_id": information["id"],
                },
            )
        )
    )
    assert reference["data"]["reference_type"] == "information"
    duplicate = _payload(
        asyncio.run(
            server.call_tool(
                "episode_reference_add",
                {
                    "episode_id": episode["id"],
                    "reference_type": "information",
                    "target_id": information["id"],
                },
            )
        )
    )
    assert duplicate["error"]["code"] == "RELATION_INTEGRITY_ERROR"
