from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import ValidationError, VersionConflictError
from novel_core.services.draft_service import DraftService
from novel_core.services.narrative_service import NarrativeService


def _open_database(db_path: Path) -> sqlite3.Connection:
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def services(tmp_path: Path):
    db_path = tmp_path / "story.db"
    connection = _open_database(db_path)
    try:
        initialize_test_work(connection, "Phase 3")
        yield SimpleNamespace(
            connection=connection,
            narrative=NarrativeService(connection),
            drafts=DraftService(connection),
        )
    finally:
        connection.close()


def _episode(services, title: str = "対象話"):
    chapter = services.narrative.create_chapter("章")
    return services.narrative.create_episode(chapter.id, title)


def test_draft_save_preserves_exact_body_and_hash(services) -> None:
    episode = _episode(services)
    body = "\n  先頭空白\n末尾改行\n"

    first = services.drafts.save_draft(
        episode.id,
        body,
        source_agent="ChatGPT",
        change_summary="初稿",
    )

    assert first.revision == 1
    assert first.parent_draft_id is None
    assert first.body == body
    assert first.content_hash == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert services.drafts.get_draft(episode.id) == first
    assert services.drafts.get_draft(episode.id, revision=1) == first


def test_draft_save_is_linear_and_history_is_metadata_only(services) -> None:
    episode = _episode(services)
    first = services.drafts.save_draft(episode.id, "revision one")
    second = services.drafts.save_draft(
        episode.id,
        "revision two",
        expected_parent_draft_id=first.id,
        source_agent="human",
        change_summary="二稿",
    )

    history = services.drafts.history(episode.id)

    assert (first.revision, second.revision) == (1, 2)
    assert [item.revision for item in history] == [1, 2]
    assert history[-1].parent_draft_id == first.id
    assert history[-1].source_agent == "human"
    assert history[-1].change_summary == "二稿"
    assert history[-1].content_hash == second.content_hash
    assert history[-1].body_chars == len("revision two")
    assert not hasattr(history[-1], "body")
    assert services.drafts.get_draft(episode.id) == second


def test_stale_parent_is_rejected_without_partial_revision(services) -> None:
    episode = _episode(services)
    first = services.drafts.save_draft(episode.id, "one")
    second = services.drafts.save_draft(
        episode.id, "two", expected_parent_draft_id=first.id
    )

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        services.drafts.save_draft(
            episode.id, "stale", expected_parent_draft_id=first.id
        )

    assert [item.revision for item in services.drafts.history(episode.id)] == [1, 2]
    assert services.drafts.get_draft(episode.id) == second


def test_draft_input_bounds_are_validated(services) -> None:
    episode = _episode(services)

    with pytest.raises(ValidationError, match="body"):
        services.drafts.save_draft(episode.id, "")
    with pytest.raises(ValidationError, match="body"):
        services.drafts.save_draft(episode.id, 123)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="source_agent"):
        services.drafts.save_draft(episode.id, "body", source_agent="")
    with pytest.raises(ValidationError, match="source_agent"):
        services.drafts.save_draft(episode.id, "body", source_agent="a" * 121)
    with pytest.raises(ValidationError, match="change_summary"):
        services.drafts.save_draft(episode.id, "body", change_summary="a" * 1001)
    with pytest.raises(ValidationError, match="limit"):
        services.drafts.history(episode.id, limit=0)
    with pytest.raises(ValidationError, match="limit"):
        services.drafts.history(episode.id, limit=101)
    with pytest.raises(ValidationError, match="revision"):
        services.drafts.get_draft(episode.id, revision=0)


def test_draft_rows_are_append_only_at_sqlite_boundary(services) -> None:
    episode = _episode(services)
    draft = services.drafts.save_draft(episode.id, "immutable")

    with pytest.raises(sqlite3.IntegrityError):
        services.connection.execute(
            "UPDATE drafts SET body = ? WHERE id = ?", ("changed", draft.id)
        )
    with pytest.raises(sqlite3.IntegrityError):
        services.connection.execute("DELETE FROM drafts WHERE id = ?", (draft.id,))
    services.connection.rollback()

    assert services.drafts.get_draft(episode.id).body == "immutable"


def test_draft_parent_foreign_key_cannot_cross_episode(services) -> None:
    first_episode = _episode(services, "第一話")
    second_episode = _episode(services, "第二話")
    first = services.drafts.save_draft(first_episode.id, "first")
    body = "invalid parent"

    with pytest.raises(sqlite3.IntegrityError):
        services.connection.execute(
            """
            INSERT INTO drafts
                (work_id, episode_id, revision, parent_draft_id, body, content_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                first.work_id,
                second_episode.id,
                1,
                first.id,
                body,
                hashlib.sha256(body.encode("utf-8")).hexdigest(),
            ),
        )
    services.connection.rollback()


def test_draft_history_limit_is_stable_and_bounded(services) -> None:
    episode = _episode(services)
    current_parent = None
    for index in range(3):
        draft = services.drafts.save_draft(
            episode.id, f"revision {index}", expected_parent_draft_id=current_parent
        )
        current_parent = draft.id

    assert [item.revision for item in services.drafts.history(episode.id, limit=2)] == [
        2,
        3,
    ]
