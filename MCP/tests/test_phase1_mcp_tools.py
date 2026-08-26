from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.types import CallToolResult

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.mcp_server import PHASE1_TOOL_NAMES, create_server


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

    assert server.tool_names() == PHASE1_TOOL_NAMES
    assert len(PHASE1_TOOL_NAMES) == 23
    assert all("chapter_" not in name for name in PHASE1_TOOL_NAMES)
    assert all("episode_" not in name for name in PHASE1_TOOL_NAMES)
    assert all("draft" not in name for name in PHASE1_TOOL_NAMES)


def test_read_and_mutation_annotations_match_tool_effects(tmp_path: Path) -> None:
    server = create_server(_config(tmp_path))
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    for name in ("work_get", "world_fact_get", "world_fact_search"):
        annotations = tools[name].annotations
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert annotations.open_world_hint is False

    assert tools["work_update"].annotations.read_only_hint is False
    assert tools["work_update"].annotations.read_only_hint is not True


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
