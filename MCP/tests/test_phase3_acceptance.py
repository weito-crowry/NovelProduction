from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.phase3_acceptance import run_phase3_acceptance


def _config(tmp_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=tmp_path / "acceptance" / "story.db",
        migration_dir=Path(__file__).resolve().parents[1] / "migrations",
    )


@pytest.fixture
def server(tmp_path: Path):
    from novel_mcp.mcp_server import create_server

    value = create_server(_config(tmp_path))
    try:
        yield value
    finally:
        value.close()


def test_real_writing_acceptance_records_each_invariant(server, tmp_path: Path) -> None:
    config = _config(tmp_path)
    initialize_work(config.db_path, "Phase 3 acceptance")
    chapter = asyncio.run(
        server.call_tool("chapter_create", {"title": "章"})
    ).structured_content["data"]
    target = asyncio.run(
        server.call_tool(
            "episode_create", {"chapter_id": chapter["id"], "title": "対象"}
        )
    ).structured_content["data"]
    future = asyncio.run(
        server.call_tool(
            "episode_create", {"chapter_id": chapter["id"], "title": "開示"}
        )
    ).structured_content["data"]
    information = asyncio.run(
        server.call_tool(
            "information_create",
            {
                "statement": "SECRET_ACCEPTANCE_PROTECTED",
                "authoring_guard": "protected plot point",
            },
        )
    ).structured_content["data"]
    asyncio.run(
        server.call_tool(
            "episode_reference_add",
            {
                "episode_id": target["id"],
                "reference_type": "information",
                "target_id": information["id"],
            },
        )
    )
    asyncio.run(
        server.call_tool(
            "reader_disclosure_set",
            {"information_item_id": information["id"], "episode_id": future["id"]},
        )
    )

    report = run_phase3_acceptance(server.database, episode_id=target["id"])

    assert report.writing_ready is True
    assert all(report.invariants.values())
    assert report.guard_present is True
    assert report.draft_append_only is True
    assert report.draft_parent_cas_ok is True
    assert report.draft_hash_ok is True
