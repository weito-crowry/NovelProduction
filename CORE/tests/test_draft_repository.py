from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.repositories.draft_repository import DraftRepository
from novel_core.services.narrative_service import NarrativeService

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"
DOCUMENT_JSON = '{"schema_version":1,"type":"novel_document","blocks":[]}'


def _connection(tmp_path: Path) -> sqlite3.Connection:
    connection = open_database(
        DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    )
    initialize_test_work(connection, "Repository test")
    chapter = NarrativeService(connection).create_chapter("Chapter")
    NarrativeService(connection).create_episode(chapter.id, "Episode")
    return connection


def test_repository_stores_only_canonical_document_json_and_raw_metadata(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    try:
        episode_id, work_id = connection.execute(
            "SELECT id, work_id FROM episodes"
        ).fetchone()
        repository = DraftRepository(connection)
        repository.begin_write()
        first_id = repository.insert(
            work_id=work_id,
            episode_id=episode_id,
            revision=1,
            parent_draft_id=None,
            document_json=DOCUMENT_JSON,
            source_agent="agent",
            change_summary="first",
        )
        repository.commit()

        record = repository.get(work_id=work_id, episode_id=episode_id, revision=1)
        assert record is not None
        assert record.id == first_id
        assert record.document_json == DOCUMENT_JSON
        assert tuple(field.name for field in dataclasses.fields(record)) == (
            "id",
            "work_id",
            "episode_id",
            "revision",
            "parent_draft_id",
            "document_json",
            "source_agent",
            "change_summary",
            "created_at",
        )
        source = (
            Path(__file__).resolve().parents[1]
            / "src/novel_core/repositories/draft_repository.py"
        )
        assert "parse_document_json" not in source.read_text(encoding="utf-8")
    finally:
        connection.close()


def test_repository_history_is_metadata_only_and_returns_newest_window_oldest_first(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    try:
        episode_id, work_id = connection.execute(
            "SELECT id, work_id FROM episodes"
        ).fetchone()
        repository = DraftRepository(connection)
        parent_id: int | None = None
        for revision in range(1, 4):
            repository.begin_write()
            parent_id = repository.insert(
                work_id=work_id,
                episode_id=episode_id,
                revision=revision,
                parent_draft_id=parent_id,
                document_json=DOCUMENT_JSON,
                source_agent=None,
                change_summary=f"r{revision}",
            )
            repository.commit()

        history = repository.history(work_id=work_id, episode_id=episode_id, limit=2)
        assert [item.revision for item in history] == [2, 3]
        assert [item.change_summary for item in history] == ["r2", "r3"]
        assert tuple(field.name for field in dataclasses.fields(history[0])) == (
            "id",
            "episode_id",
            "revision",
            "parent_draft_id",
            "source_agent",
            "change_summary",
            "created_at",
        )
    finally:
        connection.close()
