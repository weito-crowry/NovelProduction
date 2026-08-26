from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.types import CallToolResult

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.mcp_server import create_server


def _config(tmp_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=tmp_path / "acceptance" / "story.db",
        migration_dir=Path(__file__).resolve().parents[1] / "migrations",
    )


def _payload(result: CallToolResult) -> dict[str, object]:
    return result.structured_content


def test_canon_status_requires_reason_for_protected_transition(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 1")
    server = create_server(config)
    created = asyncio.run(
        server.call_tool(
            "world_fact_create",
            {"statement": "秘密", "valid_from": None, "valid_to": None},
        )
    )
    fact_id = _payload(created)["data"]["id"]

    result = asyncio.run(
        server.call_tool(
            "canon_status_set",
            {
                "entity_type": "world_fact",
                "entity_id": fact_id,
                "target_status": "canon",
                "reason": None,
            },
        )
    )

    assert _payload(result)["ok"] is False
    assert _payload(result)["error"]["code"] == "CANON_REASON_REQUIRED"


def test_tool_calls_return_json_compatible_records(tmp_path: Path) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 1")
    server = create_server(config)

    created = asyncio.run(
        server.call_tool("character_create", {"name": "葵", "profile": "観測者"})
    )
    payload = _payload(created)

    assert payload["ok"] is True
    assert payload["data"]["name"] == "葵"
    assert isinstance(payload["data"]["version"], int)


def test_server_inventory_has_no_phase_two_or_three_names(tmp_path: Path) -> None:
    server = create_server(_config(tmp_path))
    names = server.tool_names()

    assert not names & {"chapter_create", "episode_create", "scene_create"}
    assert not names & {"episode_context", "episode_draft_get", "episode_draft_save"}
