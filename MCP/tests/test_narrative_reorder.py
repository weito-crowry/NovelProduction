from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import OrderConflictError, VersionConflictError
from novel_mcp.services.narrative_service import NarrativeService


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
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)
    try:
        yield NarrativeService(connection)
    finally:
        connection.close()


def test_episode_reorder_moves_forward_and_increments_shifted_versions(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("章")
    episodes = [service.create_episode(chapter.id, f"話{i}") for i in range(1, 4)]

    reordered = service.reorder_episode(
        episodes[0].id, target_position=3, expected_version=1
    )

    assert [row.id for row in reordered] == [
        episodes[1].id,
        episodes[2].id,
        episodes[0].id,
    ]
    assert [row.position for row in reordered] == [1, 2, 3]
    assert [row.version for row in reordered] == [2, 2, 2]


def test_chapter_and_scene_reorder_move_backward(service: NarrativeService) -> None:
    chapters = [service.create_chapter(f"章{i}") for i in range(1, 4)]
    moved_chapters = service.reorder_chapter(
        chapters[2].id, target_position=1, expected_version=1
    )
    assert [row.id for row in moved_chapters] == [
        chapters[2].id,
        chapters[0].id,
        chapters[1].id,
    ]

    episode = service.create_episode(chapters[2].id, "話")
    scenes = [service.create_scene(episode.id, f"場面{i}") for i in range(1, 4)]
    moved_scenes = service.reorder_scene(
        scenes[2].id, target_position=1, expected_version=1
    )
    assert [row.id for row in moved_scenes] == [
        scenes[2].id,
        scenes[0].id,
        scenes[1].id,
    ]


def test_noop_reorder_does_not_increment_any_version(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("章")
    episodes = [service.create_episode(chapter.id, f"話{i}") for i in range(1, 3)]
    before = service.list_episodes(chapter.id)

    after = service.reorder_episode(
        episodes[0].id, target_position=1, expected_version=1
    )

    assert after == before


def test_invalid_reorder_is_atomic_and_returns_order_conflict(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("章")
    episodes = [service.create_episode(chapter.id, f"話{i}") for i in range(1, 4)]
    before = service.list_episodes(chapter.id)

    with pytest.raises(OrderConflictError, match="ORDER_CONFLICT"):
        service.reorder_episode(episodes[0].id, target_position=99, expected_version=1)

    assert service.list_episodes(chapter.id) == before


def test_stale_reorder_is_rejected_without_mutation(service: NarrativeService) -> None:
    chapter = service.create_chapter("章")
    episodes = [service.create_episode(chapter.id, f"話{i}") for i in range(1, 3)]
    service.update_episode(episodes[0].id, expected_version=1, title="改稿")
    before = service.list_episodes(chapter.id)

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.reorder_episode(episodes[0].id, target_position=2, expected_version=1)

    assert service.list_episodes(chapter.id) == before


def test_partial_forward_reorder_restores_unaffected_siblings_and_supports_follow_up(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("章")
    episodes = [service.create_episode(chapter.id, f"話{i}") for i in range(1, 6)]
    before = {row.id: row for row in service.list_episodes(chapter.id)}

    reordered = service.reorder_episode(
        episodes[1].id, target_position=3, expected_version=1
    )

    assert [row.position for row in reordered] == [1, 2, 3, 4, 5]
    assert [row.id for row in reordered] == [
        episodes[0].id,
        episodes[2].id,
        episodes[1].id,
        episodes[3].id,
        episodes[4].id,
    ]
    after = {row.id: row for row in reordered}
    for episode in (episodes[0], episodes[3], episodes[4]):
        assert after[episode.id].position == before[episode.id].position
        assert after[episode.id].version == before[episode.id].version
    for episode in (episodes[1], episodes[2]):
        assert after[episode.id].version == before[episode.id].version + 1

    followed_up = service.reorder_episode(
        episodes[1].id, target_position=4, expected_version=after[episodes[1].id].version
    )
    assert [row.position for row in followed_up] == [1, 2, 3, 4, 5]
    assert [row.id for row in followed_up] == [
        episodes[0].id,
        episodes[2].id,
        episodes[3].id,
        episodes[1].id,
        episodes[4].id,
    ]


def test_partial_backward_reorder_preserves_unaffected_positions_and_versions(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("章")
    episodes = [service.create_episode(chapter.id, f"話{i}") for i in range(1, 6)]
    before = {row.id: row for row in service.list_episodes(chapter.id)}

    reordered = service.reorder_episode(
        episodes[3].id, target_position=2, expected_version=1
    )

    assert [row.position for row in reordered] == [1, 2, 3, 4, 5]
    assert [row.id for row in reordered] == [
        episodes[0].id,
        episodes[3].id,
        episodes[1].id,
        episodes[2].id,
        episodes[4].id,
    ]
    after = {row.id: row for row in reordered}
    for episode in (episodes[0], episodes[4]):
        assert after[episode.id].position == before[episode.id].position
        assert after[episode.id].version == before[episode.id].version
    for episode in (episodes[1], episodes[2], episodes[3]):
        assert after[episode.id].version == before[episode.id].version + 1


def test_partial_reorder_then_append_uses_next_contiguous_position(
    service: NarrativeService,
) -> None:
    chapter = service.create_chapter("章")
    episodes = [service.create_episode(chapter.id, f"話{i}") for i in range(1, 6)]

    service.reorder_episode(episodes[1].id, target_position=3, expected_version=1)
    appended = service.create_episode(chapter.id, "話6")

    assert appended.position == 6
    assert [row.position for row in service.list_episodes(chapter.id)] == [1, 2, 3, 4, 5, 6]
