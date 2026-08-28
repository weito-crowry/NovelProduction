from __future__ import annotations

import ast
import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from novel_core.services.narrative_service import NarrativeService

from novel_api.app import create_app
from novel_api.config import ApiSettings

ROUTE_ROOT = Path(__file__).resolve().parents[1] / "src" / "novel_api" / "routes"
ROUTES_WITHOUT_PROJECT_CONTEXT = {"__init__.py", "health.py", "projects.py"}


def _route_methods(node: ast.FunctionDef) -> set[str]:
    return {
        decorator.func.attr.upper()
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
    }


def _service_context_calls(node: ast.FunctionDef) -> list[str]:
    return [
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in {"open_project_services", "open_project_read_services"}
    ]


def test_project_get_routes_use_only_read_project_services() -> None:
    for route_path in sorted(ROUTE_ROOT.glob("*.py")):
        if route_path.name in ROUTES_WITHOUT_PROJECT_CONTEXT:
            continue
        module = ast.parse(route_path.read_text(encoding="utf-8"))
        for node in module.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            methods = _route_methods(node)
            if not methods:
                continue
            calls = _service_context_calls(node)
            if "GET" in methods:
                assert calls == ["open_project_read_services"], (
                    route_path.name,
                    node.name,
                    calls,
                )
            else:
                assert calls == ["open_project_services"], (
                    route_path.name,
                    node.name,
                    calls,
                )


def _fingerprint(path: Path) -> tuple[bool, int, str | None]:
    if not path.exists():
        return (False, 0, None)
    content = path.read_bytes()
    return (True, len(content), hashlib.sha256(content).hexdigest())


def test_api_gets_preserve_database_and_wal_with_writer_held_open(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    project_dir = data_root / "read-only"
    project_dir.mkdir(parents=True)
    db_path = project_dir / "story.db"
    from novel_core.initialization import initialize_work

    initialize_work(db_path, working_title="Initial")
    writer = sqlite3.connect(db_path)
    chapter = NarrativeService(writer).create_chapter("Chapter")
    episode = NarrativeService(writer).create_episode(chapter.id, "Episode")
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.execute("UPDATE works SET working_title = ? WHERE id = 1", ("From WAL",))
    writer.commit()
    wal_path = Path(f"{db_path}-wal")
    assert wal_path.exists()
    before = (_fingerprint(db_path), _fingerprint(wal_path))

    try:
        app = create_app(ApiSettings(data_root=data_root))
        with TestClient(app) as client:
            responses = (
                client.get("/api/v1/projects"),
                client.get("/api/v1/projects/read-only"),
                client.get("/api/v1/projects/read-only/work"),
                client.get(
                    "/api/v1/projects/read-only/world-facts/search",
                    params={"query": "国家AI", "limit": 5},
                ),
                client.get("/api/v1/projects/read-only/chapters"),
                client.get(f"/api/v1/projects/read-only/episodes/{episode.id}/context"),
                client.get(f"/api/v1/projects/read-only/episodes/{episode.id}/drafts"),
            )
            assert all(response.status_code == 200 for response in responses), [
                response.text for response in responses
            ]
            work_payload: dict[str, Any] = responses[2].json()
            assert work_payload["data"]["working_title"] == "From WAL"

        after = (_fingerprint(db_path), _fingerprint(wal_path))
        assert after == before
    finally:
        writer.close()
