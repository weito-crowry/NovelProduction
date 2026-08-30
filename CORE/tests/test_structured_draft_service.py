from __future__ import annotations

from pathlib import Path

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import (
    DocumentSchemaError,
    DocumentStorageError,
    ValidationError,
    VersionConflictError,
)
from novel_core.services.character_service import CharacterService
from novel_core.services.draft_service import DraftService
from novel_core.services.narrative_service import NarrativeService

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture
def services(tmp_path: Path):
    connection = open_database(
        DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    )
    initialize_test_work(connection, "Structured draft service")
    narrative = NarrativeService(connection)
    chapter = narrative.create_chapter("Chapter")
    episode = narrative.create_episode(chapter.id, "Episode")
    try:
        yield (
            connection,
            episode,
            narrative,
            CharacterService(connection),
            DraftService(connection),
        )
    finally:
        connection.close()


def test_initial_plain_text_creates_canonical_document_and_result_metadata(
    services,
) -> None:
    _, episode, _, _, drafts = services

    result = drafts.save_draft(episode.id, plain_text="第一行\n第二行")
    snapshot = drafts.get_draft(episode.id)

    assert result.revision == 1
    assert result.parent_draft_id is None
    assert result.id_map == {}
    assert snapshot is not None
    assert [block.html for block in snapshot.document.blocks] == ["第一行<br>第二行"]
    assert not hasattr(snapshot, "body")


def test_initial_empty_html_and_correlation_metadata_are_valid(services) -> None:
    _, episode, narrative, _, drafts = services

    result = drafts.save_draft(
        episode.id,
        html='<p id="new-block" data-ann-emotions="[&quot;焦り&quot;]">本文</p>',
        metadata_updates={"new-block": {"attrs": {"scene_id": None}}},
    )

    assert result.revision == 1
    assert result.id_map.keys() == {"new-block"}
    snapshot = drafts.get_draft(episode.id)
    assert snapshot is not None
    assert snapshot.document.blocks[0].annotations == {"emotions": ["焦り"]}

    empty_episode = narrative.create_episode(episode.chapter_id, "Empty")
    empty = drafts.save_draft(empty_episode.id, plain_text="")
    assert empty.revision == 1


def test_save_modes_and_expected_parent_are_fail_closed(services) -> None:
    _, episode, _, _, drafts = services

    with pytest.raises(ValidationError, match="exactly one"):
        drafts.save_draft(episode.id)
    with pytest.raises(ValidationError, match="mutually exclusive"):
        drafts.save_draft(episode.id, plain_text="a", html="<p>a</p>")
    with pytest.raises(ValidationError, match="metadata_updates"):
        drafts.save_draft(episode.id, plain_text="a", metadata_updates={})

    first = drafts.save_draft(episode.id, plain_text="a")
    with pytest.raises(ValidationError, match="expected_parent"):
        drafts.save_draft(episode.id, html="<p>b</p>")
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        drafts.save_draft(
            episode.id, html="<p>b</p>", expected_parent_draft_id=first.id + 1
        )
    with pytest.raises(ValidationError, match="plain_text"):
        drafts.save_draft(
            episode.id,
            plain_text="b",
            expected_parent_draft_id=first.id,
        )


def test_restore_uses_episode_revision_number_and_does_not_copy_history_metadata(
    services,
) -> None:
    _, episode, _, _, drafts = services
    first = drafts.save_draft(
        episode.id,
        html='<p id="first">初稿</p>',
        source_agent="agent-a",
        change_summary="one",
    )
    second = drafts.save_draft(
        episode.id,
        html='<p id="first">改稿</p>',
        expected_parent_draft_id=first.id,
        source_agent="agent-b",
        change_summary="two",
    )

    restored = drafts.save_draft(
        episode.id,
        restore_revision=1,
        expected_parent_draft_id=second.id,
        source_agent="restorer",
        change_summary="restore",
    )
    snapshot = drafts.get_draft(episode.id)

    assert restored.revision == 3
    assert snapshot is not None
    assert snapshot.document.blocks[0].html == "初稿"
    assert snapshot.document.blocks[0].id == first.id_map["first"]
    assert snapshot.source_agent == "restorer"
    assert snapshot.change_summary == "restore"

    with pytest.raises(ValidationError, match="restore_revision"):
        drafts.save_draft(
            episode.id,
            restore_revision=999,
            expected_parent_draft_id=restored.id,
        )


def test_changed_live_references_are_validated_but_inherited_ones_are_not(
    services,
) -> None:
    connection, episode, narrative, characters, drafts = services
    scene = narrative.create_scene(episode.id, "Scene")
    character = characters.create("Speaker")
    first = drafts.save_draft(
        episode.id,
        html=(
            f'<p id="known" data-np-scene-id="{scene.id}" '
            f'data-np-speaker-id="{character.id}">本文</p>'
        ),
    )
    connection.execute("DELETE FROM scenes WHERE id = ?", (scene.id,))
    connection.commit()

    formal_id = first.id_map["known"]
    inherited = drafts.save_draft(
        episode.id,
        metadata_updates={formal_id: {"annotations": {"x": 1}}},
        expected_parent_draft_id=first.id,
    )
    assert inherited.revision == 2
    with pytest.raises(ValidationError, match="scene_id"):
        drafts.save_draft(
            episode.id,
            metadata_updates={formal_id: {"attrs": {"scene_id": scene.id + 99}}},
            expected_parent_draft_id=inherited.id,
        )


def test_stored_corruption_is_wrapped_without_repair(services) -> None:
    connection, episode, _, _, drafts = services
    saved = drafts.save_draft(episode.id, plain_text="valid")
    connection.execute("DROP TRIGGER drafts_append_only_update")
    connection.execute(
        "UPDATE drafts SET document_json = ? WHERE id = ?",
        ('{"schema_version":999}', saved.id),
    )
    connection.commit()

    with pytest.raises(DocumentStorageError, match="DOCUMENT_STORAGE_ERROR"):
        drafts.get_draft(episode.id)


def test_inserted_row_validation_failure_rolls_back_before_commit(
    services, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, episode, _, _, drafts = services
    first = drafts.save_draft(episode.id, plain_text="first")
    block_id = drafts.get_draft(episode.id).document.blocks[0].id
    calls = 0
    original = DraftService._snapshot_from_record

    def fail_on_inserted_row(self, record):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise DocumentSchemaError("inserted document rejected")
        return original(self, record)

    monkeypatch.setattr(DraftService, "_snapshot_from_record", fail_on_inserted_row)
    with pytest.raises(DocumentSchemaError, match="inserted document"):
        drafts.save_draft(
            episode.id,
            html=f'<p id="{block_id}">second</p>',
            expected_parent_draft_id=first.id,
        )

    assert [item.revision for item in drafts.history(episode.id)] == [1]


def test_caller_document_schema_error_remains_distinct_from_storage_error(
    services,
) -> None:
    _, episode, _, _, drafts = services

    with pytest.raises(DocumentSchemaError):
        drafts.save_draft(episode.id, html="<script>bad</script>")
