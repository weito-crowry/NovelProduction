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
                "expected_version": 1,
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


def test_timeline_event_get_retrieves_beyond_range_default_limit(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 1")
    server = create_server(config)

    event_ids = []
    for index in range(101):
        created = asyncio.run(
            server.call_tool(
                "timeline_event_create",
                {
                    "event_date": "2104-01-01",
                    "title": f"event-{index}",
                    "participants": [],
                },
            )
        )
        created_payload = _payload(created)
        assert created_payload["ok"] is True
        event_ids.append(created_payload["data"]["id"])

    result = asyncio.run(
        server.call_tool("timeline_event_get", {"event_id": event_ids[-1]})
    )

    payload = _payload(result)
    assert payload["ok"] is True
    assert payload["data"]["id"] == event_ids[-1]


def test_timeline_event_get_missing_event_returns_stable_not_found(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 1")
    server = create_server(config)

    result = asyncio.run(server.call_tool("timeline_event_get", {"event_id": 9999}))

    payload = _payload(result)
    assert payload == {
        "ok": False,
        "error": {
            "code": "NOT_FOUND",
            "message": "requested entity was not found",
        },
    }


def test_server_inventory_has_no_phase_two_or_three_names(tmp_path: Path) -> None:
    server = create_server(_config(tmp_path))
    names = server.tool_names()

    assert not names & {"chapter_create", "episode_create", "scene_create"}
    assert not names & {"episode_context", "episode_draft_get", "episode_draft_save"}


def test_mcp_search_paths_cap_limit_at_service_bound(tmp_path: Path) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 1")
    server = create_server(config)

    for index in range(101):
        fact = asyncio.run(
            server.call_tool(
                "world_fact_create",
                {
                    "statement": f"火山異常 {index}",
                    "valid_from": None,
                    "valid_to": None,
                },
            )
        )
        assert _payload(fact)["ok"] is True

    for index in range(101):
        character = asyncio.run(
            server.call_tool(
                "character_create", {"name": f"火星人物 {index}", "profile": None}
            )
        )
        assert _payload(character)["ok"] is True

    facts = asyncio.run(
        server.call_tool("world_fact_search", {"query": "火山異常", "limit": 1000})
    )
    characters = asyncio.run(
        server.call_tool("character_search", {"query": "火星人物", "limit": 1000})
    )

    assert len(_payload(facts)["data"]) == 100
    assert len(_payload(characters)["data"]) == 100
