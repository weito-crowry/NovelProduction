from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import ValidationError
from novel_core.style_analysis.source_models import (
    SourceEpisodeInput,
    SourceWorkInput,
)
from novel_core.style_analysis.source_repository import StyleSourceRepository

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"


def open_test_database(tmp_path: Path) -> sqlite3.Connection:
    return open_database(
        DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    )


def source_work(*, title: str = "Reference") -> SourceWorkInput:
    return SourceWorkInput(
        title=title,
        author_name="Author",
        metadata={"language": "ja"},
        episodes=(
            SourceEpisodeInput(
                external_episode_id="1",
                title="第一話",
                order_index=1,
                raw_text="本文一",
                metadata={"scene_break_offsets_raw": []},
            ),
            SourceEpisodeInput(
                external_episode_id="2",
                title="第二話",
                order_index=2,
                raw_text="本文二",
                metadata={"scene_break_offsets_raw": [2]},
            ),
        ),
    )


def persist_source(
    connection: sqlite3.Connection,
    *,
    repository: StyleSourceRepository | None = None,
    source_type: str = "text",
    external_work_id: str | None = None,
    payload: bytes = b"source",
) -> tuple[int, int]:
    repository = repository or StyleSourceRepository(connection)
    external_work_id = external_work_id or hashlib.sha256(payload).hexdigest()
    result = repository.insert_import(
        source_type=source_type,
        external_work_id=external_work_id,
        original_filename="book.txt",
        adapter_id="style-source-text",
        adapter_version=1,
        payload=payload,
        media_type="text/plain",
        source_metadata={},
        work=source_work(),
    )
    connection.commit()
    return result.source.id, result.work.id


def test_insert_import_persists_catalog_documents_and_current_text(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        repository = StyleSourceRepository(connection)
        payload = b"source"
        inserted = repository.insert_import(
            source_type="text",
            external_work_id=hashlib.sha256(payload).hexdigest(),
            original_filename="book.txt",
            adapter_id="style-source-text",
            adapter_version=1,
            payload=payload,
            media_type="text/plain",
            source_metadata={},
            work=source_work(),
        )
        connection.commit()

        assert inserted.source.external_work_id == hashlib.sha256(payload).hexdigest()
        assert inserted.snapshot.payload_sha256 == inserted.source.external_work_id
        assert inserted.work.episode_count == 2
        episodes = repository.list_reference_episodes(inserted.work.id)
        assert [episode.order_index for episode in episodes] == [1, 2]
        assert all(episode.style_document_id is not None for episode in episodes)
        assert [episode.current_text_revision_id for episode in episodes] == [1, 2]
        assert [episode.current_text for episode in episodes] == ["本文一", "本文二"]
        assert json.loads(episodes[1].document_metadata_json) == {
            "structure_hints": {"scene_break_offsets_cp": [2]}
        }
    finally:
        connection.close()


def test_source_identity_is_unique_and_duplicate_lookup_returns_existing_work(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        repository = StyleSourceRepository(connection)
        persist_source(connection, repository=repository)
        identity = hashlib.sha256(b"source").hexdigest()
        assert repository.find_by_identity("text", identity) is not None

        with pytest.raises(sqlite3.IntegrityError):
            repository.insert_import(
                source_type="text",
                external_work_id=identity,
                original_filename="different.txt",
                adapter_id="style-source-text",
                adapter_version=1,
                payload=b"source",
                media_type="text/plain",
                source_metadata={},
                work=source_work(title="Different"),
            )
    finally:
        connection.close()


def test_catalog_rejects_episode_snapshot_from_another_source(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        repository = StyleSourceRepository(connection)
        first_source_id, first_work_id = persist_source(connection, payload=b"one")
        second_source_id, _ = persist_source(connection, payload=b"two")
        assert first_source_id != second_source_id
        episode_id = repository.list_reference_episodes(first_work_id)[0].id
        second_snapshot_id = connection.execute(
            "SELECT id FROM style_source_snapshots WHERE source_id = ?",
            (second_source_id,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE style_reference_episodes SET latest_snapshot_id = ? WHERE id = ?",
            (second_snapshot_id, episode_id),
        )
        connection.commit()

        with pytest.raises(ValidationError, match="SOURCE_SNAPSHOT_WORK_MISMATCH"):
            repository.get_reference_episode(episode_id)
        with pytest.raises(ValidationError, match="SOURCE_SNAPSHOT_WORK_MISMATCH"):
            repository.list_reference_episodes(first_work_id)
    finally:
        connection.close()


def test_purge_source_removes_reference_graph_without_job_rows(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path)
    try:
        repository = StyleSourceRepository(connection)
        source_id, work_id = persist_source(connection)

        repository.purge_reference_work(work_id)
        connection.commit()

        for table in (
            "style_sources",
            "style_source_snapshots",
            "style_reference_works",
            "style_reference_episodes",
            "style_documents",
            "style_text_revisions",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (
                0,
            )
        assert connection.execute("SELECT COUNT(*) FROM style_jobs").fetchone() == (0,)
        assert repository.get_reference_work(work_id) is None
        assert source_id > 0
    finally:
        connection.close()
