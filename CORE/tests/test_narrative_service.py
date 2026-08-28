from __future__ import annotations

from pathlib import Path

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import ValidationError, VersionConflictError
from novel_core.services.narrative_service import NarrativeService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def service(tmp_path: Path):
    db_path = tmp_path / "story.db"
    connection = open_test_database(db_path)
    try:
        initialize_test_work(connection, "2126")
        yield NarrativeService(connection)
    finally:
        connection.close()


def test_hierarchy_crud_keeps_production_and_canon_status_separate(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter(
        "第一章", production_status="outlined", canon_status="idea"
    )
    episode = service.create_episode(chapter.id, "第一話", production_status="drafting")
    scene = service.create_scene(episode.id, "到着", production_status="final")

    assert chapter.position == episode.position == scene.position == 1
    assert chapter.production_status == "outlined"
    assert chapter.canon_status == "idea"
    assert episode.production_status == "drafting"
    assert episode.canon_status == "draft"
    assert scene.episode_id == episode.id
    assert episode.foreshadowing_notes_json == "[]"


def test_hierarchy_create_appends_within_each_parent(service: NarrativeService) -> None:
    first_chapter = service.create_chapter("第一章")
    second_chapter = service.create_chapter("第二章")
    first_episode = service.create_episode(first_chapter.id, "第一話")
    second_episode = service.create_episode(first_chapter.id, "第二話")
    service.create_episode(second_chapter.id, "別章の第一話")
    first_scene = service.create_scene(first_episode.id, "Scene 1")
    second_scene = service.create_scene(first_episode.id, "Scene 2")

    assert [row.position for row in service.list_chapters()] == [1, 2]
    assert [row.position for row in service.list_episodes(first_chapter.id)] == [1, 2]
    assert [row.position for row in service.list_scenes(first_episode.id)] == [1, 2]
    assert first_episode.position == 1
    assert second_episode.position == 2
    assert first_scene.position == 1
    assert second_scene.position == 2


def test_hierarchy_update_increments_version_and_rejects_stale_version(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("第一章")

    updated = service.update_chapter(
        chapter.id, expected_version=chapter.version, title="改稿"
    )

    assert updated.title == "改稿"
    assert updated.version == 2
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.update_chapter(
            chapter.id, expected_version=chapter.version, title="古い更新"
        )


def test_hierarchy_update_accepts_all_authoring_fields(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("第一章")
    episode = service.create_episode(chapter.id, "第一話")
    scene = service.create_scene(episode.id, "Scene")

    updated_chapter = service.update_chapter(
        chapter.id,
        expected_version=1,
        summary="要約",
        purpose="導入",
        production_status="revising",
    )
    updated_episode = service.update_episode(
        episode.id,
        expected_version=1,
        summary="話の要約",
        purpose="事件を始める",
        foreshadowing_notes=["赤い光"],
        production_status="outlined",
    )
    updated_scene = service.update_scene(
        scene.id,
        expected_version=1,
        title="Scene revised",
        summary="到着する",
        purpose="登場",
        production_status="drafting",
    )

    assert (updated_chapter.summary, updated_chapter.purpose) == ("要約", "導入")
    assert updated_episode.foreshadowing_notes_json == '["赤い光"]'
    assert updated_scene.production_status == "drafting"


def test_hierarchy_validates_statuses_and_missing_parents(
    service: NarrativeService,
) -> None:
    with pytest.raises(ValidationError, match="production_status"):
        service.create_chapter("第一章", production_status="queued")
    with pytest.raises(ValidationError, match="canon_status"):
        service.create_chapter("第一章", canon_status="published")
    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        service.create_episode(9999, "孤立した話")
    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        service.get_scene(9999)
