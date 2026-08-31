from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import ValidationError, VersionConflictError, WorkNotFoundError
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
    connection = _open_database(tmp_path / "story.db")
    try:
        initialize_test_work(connection, "Structured drafts")
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


def _canonical_json(html: str) -> str:
    return (
        '{"schema_version":1,"type":"novel_document","blocks":['
        '{"id":"blk_11111111111111111111111111111111",'
        f'"type":"narration","html":"{html}","attrs":{{}},"annotations":{{}}'
        "]}"
    )


def test_draft_save_persists_canonical_document_without_legacy_fields(services) -> None:
    episode = _episode(services)

    result = services.drafts.save_draft(
        episode.id,
        plain_text="\n  先頭空白\n末尾改行\n",
        source_agent="ChatGPT",
        change_summary="初稿",
    )

    snapshot = services.drafts.get_draft(episode.id)
    assert snapshot is not None
    assert result.revision == 1
    assert snapshot.document.blocks[0].html == "  先頭空白<br>末尾改行"
    assert not hasattr(snapshot, "body")
    assert not hasattr(snapshot, "content_hash")
    columns = {
        row[1] for row in services.connection.execute("PRAGMA table_info(drafts)")
    }
    assert "document_json" in columns
    assert "body" not in columns
    assert "content_hash" not in columns


def test_draft_save_is_linear_and_history_is_metadata_only(services) -> None:
    episode = _episode(services)
    first = services.drafts.save_draft(episode.id, plain_text="revision one")
    second = services.drafts.save_draft(
        episode.id,
        html='<p id="known">revision two</p>',
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
    assert not hasattr(history[-1], "body")
    assert not hasattr(history[-1], "content_hash")
    assert services.drafts.get_draft(episode.id).revision == 2


def test_latest_metadata_uses_latest_revision_without_document_payload(
    services,
) -> None:
    first_episode = _episode(services, "第一話")
    second_episode = _episode(services, "第二話")
    first = services.drafts.save_draft(first_episode.id, plain_text="first")
    services.drafts.save_draft(
        first_episode.id,
        html='<p id="known">second</p>',
        expected_parent_draft_id=first.id,
    )
    services.drafts.save_draft(second_episode.id, plain_text="other")

    metadata = services.drafts.latest_metadata()

    assert [(item.episode_id, item.revision) for item in metadata] == [
        (first_episode.id, 2),
        (second_episode.id, 1),
    ]
    assert not hasattr(metadata[0], "document_json")


def test_latest_metadata_matches_work_not_found_contract(tmp_path: Path) -> None:
    connection = _open_database(tmp_path / "story.db")
    try:
        with pytest.raises(WorkNotFoundError, match="WORK_NOT_FOUND"):
            DraftService(connection).latest_metadata()
    finally:
        connection.close()


def test_stale_parent_is_rejected_without_partial_revision(services) -> None:
    episode = _episode(services)
    first = services.drafts.save_draft(episode.id, plain_text="one")
    second = services.drafts.save_draft(
        episode.id,
        html='<p id="known">two</p>',
        expected_parent_draft_id=first.id,
    )

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        services.drafts.save_draft(
            episode.id,
            html='<p id="known">stale</p>',
            expected_parent_draft_id=first.id,
        )

    assert [item.revision for item in services.drafts.history(episode.id)] == [1, 2]
    assert services.drafts.get_draft(episode.id).id == second.id


def test_draft_input_bounds_and_initial_modes_are_validated(services) -> None:
    episode = _episode(services)

    with pytest.raises(ValidationError, match="exactly one"):
        services.drafts.save_draft(episode.id)
    with pytest.raises(ValidationError, match="plain_text"):
        services.drafts.save_draft(episode.id, plain_text=123)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="mutually exclusive"):
        services.drafts.save_draft(episode.id, plain_text="a", html="<p>a</p>")
    with pytest.raises(ValidationError, match="source_agent"):
        services.drafts.save_draft(episode.id, plain_text="body", source_agent="")
    with pytest.raises(ValidationError, match="source_agent"):
        services.drafts.save_draft(
            episode.id, plain_text="body", source_agent="a" * 121
        )
    with pytest.raises(ValidationError, match="change_summary"):
        services.drafts.save_draft(
            episode.id, plain_text="body", change_summary="a" * 1001
        )
    with pytest.raises(ValidationError, match="limit"):
        services.drafts.history(episode.id, limit=0)
    with pytest.raises(ValidationError, match="limit"):
        services.drafts.history(episode.id, limit=101)
    with pytest.raises(ValidationError, match="revision"):
        services.drafts.get_draft(episode.id, revision=0)


def test_draft_rows_are_append_only_at_sqlite_boundary(services) -> None:
    episode = _episode(services)
    draft = services.drafts.save_draft(episode.id, plain_text="immutable")

    with pytest.raises(sqlite3.IntegrityError):
        services.connection.execute(
            "UPDATE drafts SET document_json = ? WHERE id = ?",
            (_canonical_json("changed"), draft.id),
        )
    with pytest.raises(sqlite3.IntegrityError):
        services.connection.execute("DELETE FROM drafts WHERE id = ?", (draft.id,))
    services.connection.rollback()

    assert services.drafts.get_draft(episode.id).document.blocks[0].html == "immutable"


def test_draft_parent_foreign_key_cannot_cross_episode(services) -> None:
    first_episode = _episode(services, "第一話")
    second_episode = _episode(services, "第二話")
    first = services.drafts.save_draft(first_episode.id, plain_text="first")
    second_work_id = services.connection.execute(
        "SELECT work_id FROM episodes WHERE id = ?", (second_episode.id,)
    ).fetchone()[0]

    with pytest.raises(sqlite3.IntegrityError):
        services.connection.execute(
            """
            INSERT INTO drafts
                (work_id, episode_id, revision, parent_draft_id, document_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                second_work_id,
                second_episode.id,
                1,
                first.id,
                _canonical_json("invalid"),
            ),
        )
    services.connection.rollback()


def test_draft_history_limit_is_stable_and_bounded(services) -> None:
    episode = _episode(services)
    first = services.drafts.save_draft(episode.id, plain_text="revision 0")
    current_parent = first.id
    for index in range(1, 3):
        block_id = services.drafts.get_draft(episode.id).document.blocks[0].id
        draft = services.drafts.save_draft(
            episode.id,
            html=f'<p id="{block_id}">revision {index}</p>',
            expected_parent_draft_id=current_parent,
        )
        current_parent = draft.id

    assert [item.revision for item in services.drafts.history(episode.id, limit=2)] == [
        2,
        3,
    ]
