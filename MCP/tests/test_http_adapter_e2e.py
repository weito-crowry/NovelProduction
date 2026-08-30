from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Any

import pytest

from novel_mcp.api_client import ApiClient
from novel_mcp.config import McpSettings
from novel_mcp.phase1_tools import register_phase1_tools
from novel_mcp.phase2_tools import register_phase2_tools
from novel_mcp.phase3_tools import register_phase3_tools
from novel_mcp.project_tools import register_project_tools

_LOOP = asyncio.new_event_loop()


def _run(coroutine: Any) -> Any:
    return _LOOP.run_until_complete(coroutine)


def test_real_mcp_http_e2e_covers_isolation_search_write_conflicts_and_drafts(
    api_url: str,
) -> None:
    client = ApiClient(McpSettings(api_url))
    handlers: dict[str, Any] = {}

    def register(name: str, handler: Any, **_: Any) -> None:
        handlers[name] = handler

    register_project_tools(client, register)
    register_phase1_tools(client, register)
    register_phase2_tools(client, register)
    register_phase3_tools(client, register)
    try:
        project_a = _ok(
            _run(handlers["project_create"](working_title="A", project_id="project-a"))
        )
        project_b = _ok(
            _run(handlers["project_create"](working_title="B", project_id="project-b"))
        )
        assert project_a["project_id"] == "project-a"
        assert project_b["project_id"] == "project-b"

        fact_a = _ok(
            _run(
                handlers["world_fact_create"](
                    project_id="project-a", statement="fact only A"
                )
            )
        )
        fact_b = _ok(
            _run(
                handlers["world_fact_create"](
                    project_id="project-b", statement="fact only B"
                )
            )
        )
        search_a = _ok(
            _run(handlers["world_fact_search"](project_id="project-a", query="fact"))
        )
        search_b = _ok(
            _run(handlers["world_fact_search"](project_id="project-b", query="fact"))
        )
        assert [row["id"] for row in search_a] == [fact_a["id"]]
        assert [row["id"] for row in search_b] == [fact_b["id"]]
        assert all(row["statement"] != "fact only B" for row in search_a)
        assert all(row["statement"] != "fact only A" for row in search_b)

        updated = _ok(
            _run(
                handlers["world_fact_update"](
                    project_id="project-a",
                    fact_id=fact_a["id"],
                    statement="fact A updated",
                    expected_version=fact_a["version"],
                )
            )
        )
        assert updated["statement"] == "fact A updated"
        stale = _run(
            handlers["world_fact_update"](
                project_id="project-a",
                fact_id=fact_a["id"],
                statement="stale",
                expected_version=fact_a["version"],
            )
        )
        assert stale["ok"] is False
        assert stale["error"]["code"] == "VERSION_CONFLICT"
        assert stale["error"]["project_id"] == "project-a"
        assert stale["error"]["details"]["expected_version"] == fact_a["version"]
        assert stale["error"]["details"]["current_version"] == updated["version"]
        assert stale["error"]["details"]["current_resource"]["id"] == fact_a["id"]

        chapter = _ok(
            _run(handlers["chapter_create"](project_id="project-a", title="章"))
        )
        episode = _ok(
            _run(
                handlers["episode_create"](
                    project_id="project-a", chapter_id=chapter["id"], title="話"
                )
            )
        )
        assert _ok(
            _run(
                handlers["episode_outline_get"](
                    project_id="project-a", episode_id=episode["id"]
                )
            )
        )
        assert _ok(
            _run(
                handlers["episode_context"](
                    project_id="project-a", episode_id=episode["id"]
                )
            )
        )
        first = _ok(
            _run(
                handlers["episode_draft_save"](
                    project_id="project-a", episode_id=episode["id"], plain_text="初稿"
                )
            )
        )
        second = _ok(
            _run(
                handlers["episode_draft_save"](
                    project_id="project-a",
                    episode_id=episode["id"],
                    html="<p>第二稿</p>",
                    expected_parent_draft_id=first["id"],
                )
            )
        )
        latest = _ok(
            _run(
                handlers["episode_draft_get"](
                    project_id="project-a", episode_id=episode["id"]
                )
            )
        )
        history = _ok(
            _run(
                handlers["episode_draft_history"](
                    project_id="project-a", episode_id=episode["id"]
                )
            )
        )
        assert latest["format"] == "html"
        assert latest["content"].endswith('" data-np-type="narration">第二稿</p>')
        assert [item["revision"] for item in history] == [1, 2]
        stale_parent = _run(
            handlers["episode_draft_save"](
                project_id="project-a",
                episode_id=episode["id"],
                html="<p>競合稿</p>",
                expected_parent_draft_id=first["id"],
            )
        )
        assert stale_parent["ok"] is False
        assert stale_parent["error"]["code"] == "VERSION_CONFLICT"
        assert stale_parent["error"]["details"]["expected_version"] == first["id"]
        assert stale_parent["error"]["details"]["current_version"] == second["id"]
        assert (
            stale_parent["error"]["details"]["current_resource"]["id"] == second["id"]
        )
    finally:
        _run(client.aclose())


def test_real_mcp_http_e2e_maps_unreachable_backend_without_db_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    client = ApiClient(McpSettings(f"http://127.0.0.1:{_unused_port()}"))
    handlers: dict[str, Any] = {}
    register_project_tools(
        client, lambda name, handler, **_: handlers.update({name: handler})
    )
    try:
        result = _run(handlers["project_get"](project_id="project-a"))
    finally:
        _run(client.aclose())

    assert result == {
        "ok": False,
        "error": {
            "code": "BACKEND_UNAVAILABLE",
            "message": "NovelProduction API is unavailable.",
            "project_id": "project-a",
            "details": {},
        },
    }
    assert list(tmp_path.rglob("*.db")) == []


def _ok(result: Any) -> Any:
    assert result["ok"] is True, result
    return result["data"]


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
