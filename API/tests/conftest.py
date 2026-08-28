from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from novel_core.initialization import initialize_work

from novel_api.app import create_app
from novel_api.config import ApiSettings

_NO_METADATA = object()


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root


@pytest.fixture
def client(data_root: Path) -> Iterator[TestClient]:
    app = create_app(ApiSettings(data_root=data_root))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def project_factory(data_root: Path):
    def factory(
        project_id: str,
        *,
        working_title: str = "Project",
        metadata: object = _NO_METADATA,
        create_story_db: bool = True,
        story_db_bytes: bytes | None = None,
    ) -> Path:
        project_dir = data_root / project_id
        project_dir.mkdir(parents=True, exist_ok=False)

        if create_story_db:
            story_db_path = project_dir / "story.db"
            if story_db_bytes is None:
                initialize_work(story_db_path, working_title=working_title)
            else:
                story_db_path.write_bytes(story_db_bytes)

        if metadata is not _NO_METADATA:
            metadata_path = project_dir / "project.json"
            if isinstance(metadata, bytes):
                metadata_path.write_bytes(metadata)
            elif isinstance(metadata, str):
                metadata_path.write_text(metadata, encoding="utf-8")
            else:
                metadata_path.write_text(
                    json.dumps(metadata, ensure_ascii=False),
                    encoding="utf-8",
                )

        return project_dir

    return factory


def read_working_title(story_db_path: Path) -> str:
    connection = sqlite3.connect(story_db_path)
    try:
        row = connection.execute("SELECT working_title FROM works").fetchone()
        assert row is not None
        return str(row[0])
    finally:
        connection.close()


def read_project_metadata(project_dir: Path) -> dict[str, Any]:
    return json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
