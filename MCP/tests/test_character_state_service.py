from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import ValidationError, VersionConflictError, WorkScopeError
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.character_state_service import CharacterStateService
from novel_mcp.services.narrative_service import NarrativeService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def services(tmp_path: Path):
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)
    try:
        yield type(
            "Services",
            (),
            {
                "connection": connection,
                "character": CharacterService(connection),
                "narrative": NarrativeService(connection),
                "state": CharacterStateService(connection),
            },
        )()
    finally:
        connection.close()


def test_state_is_a_change_log_with_effective_narrative_order(services) -> None:
    character = services.character.create("主人公")
    chapter = services.narrative.create_chapter("章")
    episodes = [
        services.narrative.create_episode(chapter.id, f"話{i}") for i in range(1, 4)
    ]
    first = services.state.set_state(
        character.id, episodes[0].id, physical_state="healthy"
    )
    second = services.state.set_state(
        character.id, episodes[1].id, physical_state="injured"
    )
    future = services.state.set_state(
        character.id, episodes[2].id, physical_state="recovered"
    )

    assert first.version == second.version == future.version == 1
    assert services.state.get_effective_state(character.id, episodes[0].id) == first
    assert services.state.get_effective_state(character.id, episodes[1].id) == second
    assert services.state.history(character.id) == (first, second, future)


def test_same_episode_state_change_requires_expected_version(services) -> None:
    character = services.character.create("主人公")
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "話")
    initial = services.state.set_state(character.id, episode.id, emotional_state="平静")

    with pytest.raises(ValidationError, match="expected_version"):
        services.state.set_state(character.id, episode.id, emotional_state="動揺")
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        services.state.set_state(
            character.id,
            episode.id,
            emotional_state="動揺",
            expected_version=999,
        )
    updated = services.state.set_state(
        character.id,
        episode.id,
        emotional_state="動揺",
        expected_version=initial.version,
    )
    assert (updated.emotional_state, updated.version) == ("動揺", 2)


def test_effective_state_changes_when_episode_order_changes(services) -> None:
    character = services.character.create("主人公")
    chapter = services.narrative.create_chapter("章")
    first = services.narrative.create_episode(chapter.id, "第一話")
    second = services.narrative.create_episode(chapter.id, "第二話")
    third = services.narrative.create_episode(chapter.id, "第三話")
    services.state.set_state(character.id, first.id, physical_state="healthy")
    changed = services.state.set_state(
        character.id, second.id, physical_state="injured"
    )

    assert services.state.get_effective_state(character.id, third.id) == changed
    services.narrative.reorder_episode(second.id, target_position=1, expected_version=1)

    effective = services.state.get_effective_state(character.id, third.id)
    assert effective is not None
    assert effective.physical_state == "healthy"


def test_state_validates_json_and_configured_work_scope(services) -> None:
    character = services.character.create("主人公")
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "話")
    with pytest.raises(ValidationError, match="beliefs_json"):
        services.state.set_state(character.id, episode.id, beliefs_json="not-json")

    connection = services.connection
    connection.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("other", "Other"),
    )
    other_work_id = connection.execute(
        "SELECT id FROM works WHERE slug = 'other'"
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO characters "
        "(work_id, character_key, display_name, entity_type) VALUES (?, ?, ?, ?)",
        (other_work_id, "other-character", "別人", "human"),
    )
    other_character_id = connection.execute(
        "SELECT id FROM characters WHERE character_key = 'other-character'"
    ).fetchone()[0]
    connection.commit()
    with pytest.raises(WorkScopeError, match="WORK_SCOPE_ERROR"):
        services.state.set_state(other_character_id, episode.id, physical_state="x")
