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
    PHASE3_TOOL_NAMES,
    create_server,
)


def _config(tmp_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=tmp_path / "isolated" / "story.db",
        migration_dir=Path(__file__).resolve().parents[2] / "CORE" / "migrations",
    )


@pytest.fixture
def server(tmp_path: Path):
    value = create_server(_config(tmp_path))
    try:
        yield value
    finally:
        value.close()


def _structured(result: CallToolResult) -> dict[str, object]:
    content = result.structured_content
    if content is not None:
        return content
    text = result.content[0].text
    return json.loads(text)


def test_server_preserves_phase1_tools_and_adds_phase2_tools(server) -> None:
    expected_tool_names = {
        "work_get",
        "work_update",
        "world_fact_create",
        "world_fact_update",
        "world_fact_get",
        "world_fact_search",
        "timeline_event_create",
        "timeline_event_update",
        "timeline_event_get",
        "timeline_event_search",
        "timeline_range",
        "timeline_move",
        "timeline_relation_create",
        "character_create",
        "character_update",
        "character_get",
        "character_search",
        "relationship_create",
        "relationship_update",
        "relationship_search",
        "canon_status_set",
        "canon_decision_get",
        "canon_decision_search",
    }

    assert (
        server.tool_names()
        == expected_tool_names | PHASE2_TOOL_NAMES | PHASE3_TOOL_NAMES
    )
    assert expected_tool_names == PHASE1_TOOL_NAMES
    assert len(server.tool_names()) == 55


def test_read_and_mutation_annotations_match_tool_effects(server) -> None:
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    expected_annotations = {
        "work_get": (True, False),
        "work_update": (False, True),
        "world_fact_create": (False, False),
        "world_fact_update": (False, True),
        "world_fact_get": (True, False),
        "world_fact_search": (True, False),
        "timeline_event_create": (False, False),
        "timeline_event_update": (False, True),
        "timeline_event_get": (True, False),
        "timeline_event_search": (True, False),
        "timeline_range": (True, False),
        "timeline_move": (False, True),
        "timeline_relation_create": (False, False),
        "character_create": (False, False),
        "character_update": (False, True),
        "character_get": (True, False),
        "character_search": (True, False),
        "relationship_create": (False, False),
        "relationship_update": (False, True),
        "relationship_search": (True, False),
        "canon_status_set": (False, True),
        "canon_decision_get": (True, False),
        "canon_decision_search": (True, False),
    }

    assert set(expected_annotations) == PHASE1_TOOL_NAMES
    assert PHASE1_TOOL_NAMES <= set(tools)
    for name, (read_only, destructive) in expected_annotations.items():
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is read_only
        assert annotations.destructive_hint is destructive
        assert annotations.open_world_hint is False

    assert "expected_version" in tools["canon_status_set"].input_schema["required"]


def test_all_phase1_tools_have_actionable_descriptions_and_schema_bounds(
    server,
) -> None:
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert PHASE1_TOOL_NAMES <= set(tools)
    for tool in tools.values():
        assert tool.description
        assert tool.description.startswith("Use this when")
    assert (
        tools["world_fact_search"].input_schema["properties"]["limit"]["maximum"] == 100
    )
    date_precision_schema = tools["timeline_event_create"].input_schema["properties"][
        "date_precision"
    ]
    assert date_precision_schema["anyOf"][0]["enum"] == [
        "unknown",
        "year",
        "season",
        "month",
        "day",
    ]
    assert tools["character_create"].input_schema["properties"]["entity_type"][
        "enum"
    ] == ["human", "ai", "organization"]
    assert tools["canon_status_set"].input_schema["properties"]["target_status"][
        "enum"
    ] == ["idea", "draft", "canon", "deprecated"]
    assert tools["canon_status_set"].input_schema["properties"]["entity_type"][
        "enum"
    ] == [
        "world_fact",
        "timeline_event",
        "character",
        "relationship",
        "chapter",
        "episode",
        "scene",
        "information_item",
    ]
    assert tools["work_update"].input_schema["properties"]["production_status"][
        "anyOf"
    ][0]["enum"] == ["planned", "outlined", "drafting", "revising", "final"]


def test_relationship_tools_expose_temporal_bounds_and_clear_nullable_boundaries(
    server, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 2")
    first_character = _structured(
        asyncio.run(server.call_tool("character_create", {"display_name": "A"}))
    )["data"]
    second_character = _structured(
        asyncio.run(server.call_tool("character_create", {"display_name": "B"}))
    )["data"]
    chapter = _structured(
        asyncio.run(server.call_tool("chapter_create", {"title": "章"}))
    )["data"]
    first_episode = _structured(
        asyncio.run(
            server.call_tool(
                "episode_create",
                {"chapter_id": chapter["id"], "title": "第一話"},
            )
        )
    )["data"]
    second_episode = _structured(
        asyncio.run(
            server.call_tool(
                "episode_create",
                {"chapter_id": chapter["id"], "title": "第二話"},
            )
        )
    )["data"]
    third_episode = _structured(
        asyncio.run(
            server.call_tool(
                "episode_create",
                {"chapter_id": chapter["id"], "title": "第三話"},
            )
        )
    )["data"]

    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    create_properties = tools["relationship_create"].input_schema["properties"]
    update_properties = tools["relationship_update"].input_schema["properties"]
    for properties in (create_properties, update_properties):
        assert properties["valid_from_episode_id"]["anyOf"][0]["minimum"] == 1
        assert properties["valid_to_episode_id"]["anyOf"][0]["minimum"] == 1
    assert update_properties["clear_valid_from"]["default"] is False
    assert update_properties["clear_valid_to"]["default"] is False

    created = _structured(
        asyncio.run(
            server.call_tool(
                "relationship_create",
                {
                    "source_character_id": first_character["id"],
                    "target_character_id": second_character["id"],
                    "relationship_type": "ally",
                    "valid_from_episode_id": first_episode["id"],
                    "valid_to_episode_id": second_episode["id"],
                },
            )
        )
    )
    assert created["ok"] is True
    relationship = created["data"]
    assert relationship["valid_from_episode_id"] == first_episode["id"]
    assert relationship["valid_to_episode_id"] == second_episode["id"]

    updated = _structured(
        asyncio.run(
            server.call_tool(
                "relationship_update",
                {
                    "relationship_id": relationship["id"],
                    "expected_version": relationship["version"],
                    "relationship_type": "ally",
                    "valid_to_episode_id": third_episode["id"],
                },
            )
        )
    )
    assert updated["ok"] is True
    assert updated["data"]["valid_from_episode_id"] == first_episode["id"]
    assert updated["data"]["valid_to_episode_id"] == third_episode["id"]

    cleared_start = _structured(
        asyncio.run(
            server.call_tool(
                "relationship_update",
                {
                    "relationship_id": relationship["id"],
                    "expected_version": updated["data"]["version"],
                    "relationship_type": "ally",
                    "clear_valid_from": True,
                },
            )
        )
    )
    assert cleared_start["ok"] is True
    assert cleared_start["data"]["valid_from_episode_id"] is None

    cleared_end = _structured(
        asyncio.run(
            server.call_tool(
                "relationship_update",
                {
                    "relationship_id": relationship["id"],
                    "expected_version": cleared_start["data"]["version"],
                    "relationship_type": "ally",
                    "clear_valid_to": True,
                },
            )
        )
    )
    assert cleared_end["ok"] is True
    assert cleared_end["data"]["valid_to_episode_id"] is None

    conflicting = _structured(
        asyncio.run(
            server.call_tool(
                "relationship_update",
                {
                    "relationship_id": relationship["id"],
                    "expected_version": cleared_end["data"]["version"],
                    "relationship_type": "ally",
                    "valid_from_episode_id": first_episode["id"],
                    "clear_valid_from": True,
                },
            )
        )
    )
    assert conflicting["ok"] is False
    assert conflicting["error"]["code"] == "VALIDATION_ERROR"


def test_canon_status_set_exposes_phase2_entities_and_preserves_policy(
    server, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 2")
    chapter = _structured(
        asyncio.run(server.call_tool("chapter_create", {"title": "章"}))
    )["data"]
    episode = _structured(
        asyncio.run(
            server.call_tool(
                "episode_create", {"chapter_id": chapter["id"], "title": "話"}
            )
        )
    )["data"]
    scene = _structured(
        asyncio.run(
            server.call_tool(
                "scene_create", {"episode_id": episode["id"], "title": "場面"}
            )
        )
    )["data"]
    information = _structured(
        asyncio.run(server.call_tool("information_create", {"statement": "情報"}))
    )["data"]

    for entity_type, entity in (
        ("chapter", chapter),
        ("episode", episode),
        ("scene", scene),
        ("information_item", information),
    ):
        result = _structured(
            asyncio.run(
                server.call_tool(
                    "canon_status_set",
                    {
                        "entity_type": entity_type,
                        "entity_id": entity["id"],
                        "target_status": "canon",
                        "expected_version": 1,
                        "reason": "採用理由",
                    },
                )
            )
        )
        assert result["ok"] is True

    missing_reason = _structured(
        asyncio.run(
            server.call_tool(
                "canon_status_set",
                {
                    "entity_type": "chapter",
                    "entity_id": chapter["id"],
                    "target_status": "deprecated",
                    "expected_version": 2,
                },
            )
        )
    )
    assert missing_reason["error"]["code"] == "CANON_REASON_REQUIRED"

    deprecated = _structured(
        asyncio.run(
            server.call_tool(
                "canon_status_set",
                {
                    "entity_type": "chapter",
                    "entity_id": chapter["id"],
                    "target_status": "deprecated",
                    "expected_version": 2,
                    "reason": "撤回",
                },
            )
        )
    )
    assert deprecated["ok"] is True
    rejected = _structured(
        asyncio.run(
            server.call_tool(
                "canon_status_set",
                {
                    "entity_type": "chapter",
                    "entity_id": chapter["id"],
                    "target_status": "canon",
                    "expected_version": 3,
                    "reason": "復帰",
                },
            )
        )
    )
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "CANON_POLICY_ERROR"


def test_work_get_returns_structured_json_and_does_not_create_work(
    server,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    result = asyncio.run(server.call_tool("work_get", {}))

    payload = _structured(result)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_FOUND"
    initialize_work(config.db_path, "Phase 1")
    result = asyncio.run(server.call_tool("work_get", {}))
    payload = _structured(result)
    assert payload["ok"] is True
    assert payload["data"]["working_title"] == "Phase 1"


def test_validation_and_version_errors_are_stable_and_do_not_leak_sqlite(
    server,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 1")

    invalid = asyncio.run(
        server.call_tool("work_update", {"working_title": "", "expected_version": 1})
    )
    updated = asyncio.run(
        server.call_tool(
            "work_update",
            {
                "working_title": "updated",
                "genre": "SF",
                "premise": "A premise",
                "themes_json": '["identity"]',
                "description": "A description",
                "production_status": "outlined",
                "expected_version": 1,
            },
        )
    )
    stale = asyncio.run(
        server.call_tool(
            "work_update", {"working_title": "updated", "expected_version": 999}
        )
    )

    assert _structured(invalid)["error"]["code"] == "VALIDATION_ERROR"
    updated_payload = _structured(updated)
    assert updated_payload["ok"] is True
    assert updated_payload["data"]["working_title"] == "updated"
    assert updated_payload["data"]["themes_json"] == '["identity"]'
    assert updated_payload["data"]["production_status"] == "outlined"
    assert _structured(stale)["error"]["code"] == "VERSION_CONFLICT"
    assert "sqlite" not in json.dumps(_structured(stale)).lower()
