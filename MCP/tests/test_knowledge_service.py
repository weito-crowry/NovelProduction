from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import ValidationError, VersionConflictError
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.information_service import InformationService
from novel_mcp.services.knowledge_service import KnowledgeService
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
                "information": InformationService(connection),
                "narrative": NarrativeService(connection),
                "knowledge": KnowledgeService(connection),
            },
        )()
    finally:
        connection.close()


def test_false_information_can_be_believed_and_is_structured(services) -> None:
    character = services.character.create("主人公")
    item = services.information.create_information("偽の噂", truth_status="false")
    chapter = services.narrative.create_chapter("章")
    first = services.narrative.create_episode(chapter.id, "第一話")
    second = services.narrative.create_episode(chapter.id, "第二話")

    event = services.knowledge.set_character_knowledge(
        character.id,
        item.id,
        second.id,
        "believes",
        expected_version=None,
    )

    assert services.knowledge.get_character_knowledge(character.id, first.id) == ()
    result = services.knowledge.get_character_knowledge(character.id, second.id)
    assert len(result) == 1
    assert result[0].knowledge_state == "believes"
    assert result[0].event_episode_id == second.id
    assert result[0].information_item.truth_status == "false"
    assert event.version == 1


def test_knowledge_event_cas_and_future_exclusion(services) -> None:
    character = services.character.create("主人公")
    item = services.information.create_information("情報")
    chapter = services.narrative.create_chapter("章")
    first = services.narrative.create_episode(chapter.id, "第一話")
    second = services.narrative.create_episode(chapter.id, "第二話")
    event = services.knowledge.set_character_knowledge(
        character.id, item.id, first.id, "suspects", expected_version=None
    )

    with pytest.raises(ValidationError, match="expected_version"):
        services.knowledge.set_character_knowledge(
            character.id, item.id, first.id, "knows"
        )
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        services.knowledge.set_character_knowledge(
            character.id, item.id, first.id, "knows", expected_version=999
        )
    updated = services.knowledge.set_character_knowledge(
        character.id, item.id, first.id, "knows", expected_version=event.version
    )
    assert updated.version == 2
    assert (
        services.knowledge.get_character_knowledge(character.id, second.id)[
            0
        ].knowledge_state
        == "knows"
    )


def test_effective_knowledge_uses_current_narrative_order(services) -> None:
    character = services.character.create("主人公")
    item = services.information.create_information("情報")
    chapter = services.narrative.create_chapter("章")
    first = services.narrative.create_episode(chapter.id, "第一話")
    second = services.narrative.create_episode(chapter.id, "第二話")
    third = services.narrative.create_episode(chapter.id, "第三話")
    services.knowledge.set_character_knowledge(
        character.id, item.id, first.id, "suspects", expected_version=None
    )
    services.knowledge.set_character_knowledge(
        character.id, item.id, second.id, "knows", expected_version=None
    )

    assert (
        services.knowledge.get_character_knowledge(character.id, third.id)[
            0
        ].knowledge_state
        == "knows"
    )
    services.narrative.reorder_episode(second.id, 1, second.version)

    result = services.knowledge.get_character_knowledge(character.id, third.id)
    assert result[0].knowledge_state == "suspects"
    assert result[0].event_episode_id == first.id


def test_deprecated_information_is_excluded_from_effective_knowledge(services) -> None:
    character = services.character.create("主人公")
    item = services.information.create_information("撤回情報")
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "第一話")
    services.knowledge.set_character_knowledge(
        character.id, item.id, episode.id, "knows", expected_version=None
    )

    canon = CanonService(services.connection)
    canon.set_canon_status("information_item", item.id, "canon", 1, "採用")
    canon.set_canon_status("information_item", item.id, "deprecated", 2, "撤回")

    assert services.knowledge.get_character_knowledge(character.id, episode.id) == ()
    assert services.knowledge.get_known_information(character.id, episode.id) == ()
