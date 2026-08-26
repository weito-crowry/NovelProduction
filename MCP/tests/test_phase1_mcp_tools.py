from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.types import CallToolResult

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.mcp_server import create_server


def _config(tmp_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=tmp_path / "isolated" / "story.db",
        migration_dir=Path(__file__).resolve().parents[1] / "migrations",
    )


def _structured(result: CallToolResult) -> dict[str, object]:
    content = result.structured_content
    if content is not None:
        return content
    text = result.content[0].text
    return json.loads(text)


def test_phase1_server_registers_only_planned_tools(tmp_path: Path) -> None:
    server = create_server(_config(tmp_path))

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

    assert server.tool_names() == expected_tool_names
    assert len(expected_tool_names) == 23


def test_read_and_mutation_annotations_match_tool_effects(tmp_path: Path) -> None:
    server = create_server(_config(tmp_path))
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

    assert set(tools) == set(expected_annotations)
    for name, (read_only, destructive) in expected_annotations.items():
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is read_only
        assert annotations.destructive_hint is destructive
        assert annotations.open_world_hint is False

    assert "expected_version" in tools["canon_status_set"].input_schema["required"]


def test_work_get_returns_structured_json_and_does_not_create_work(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    server = create_server(config)

    result = asyncio.run(server.call_tool("work_get", {}))

    payload = _structured(result)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_FOUND"
    initialize_work(config.db_path, "Phase 1")
    server = create_server(config)
    result = asyncio.run(server.call_tool("work_get", {}))
    payload = _structured(result)
    assert payload["ok"] is True
    assert payload["data"]["title"] == "Phase 1"


def test_validation_and_version_errors_are_stable_and_do_not_leak_sqlite(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 1")
    server = create_server(config)

    invalid = asyncio.run(
        server.call_tool("work_update", {"title": "", "expected_version": 1})
    )
    stale = asyncio.run(
        server.call_tool("work_update", {"title": "updated", "expected_version": 999})
    )

    assert _structured(invalid)["error"]["code"] == "VALIDATION_ERROR"
    assert _structured(stale)["error"]["code"] == "VERSION_CONFLICT"
    assert "sqlite" not in json.dumps(_structured(stale)).lower()
