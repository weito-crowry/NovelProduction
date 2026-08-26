from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import RelationshipIntegrityError, ValidationError
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.episode_reference_service import EpisodeReferenceService
from novel_mcp.services.information_service import InformationService
from novel_mcp.services.narrative_service import NarrativeService
from novel_mcp.services.timeline_service import TimelineService
from novel_mcp.services.world_fact_service import WorldFactService


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
                "reference": EpisodeReferenceService(connection),
                "timeline": TimelineService(connection),
                "world_fact": WorldFactService(connection),
            },
        )()
    finally:
        connection.close()


def test_episode_references_cover_all_targets_and_filter(services) -> None:
    character = services.character.create("主人公")
    fact = services.world_fact.create("都市が存在する")
    event = services.timeline.create_event(title="停電")
    item = services.information.create_information("秘密")
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "第一話")

    references = (
        services.reference.add(episode.id, "character", character.id, role="viewpoint"),
        services.reference.add(episode.id, "world_fact", fact.id),
        services.reference.add(episode.id, "timeline_event", event.id),
        services.reference.add(episode.id, "information", item.id),
    )

    assert [reference.reference_type for reference in references] == [
        "character",
        "world_fact",
        "timeline_event",
        "information",
    ]
    assert references[0].role == "viewpoint"
    assert services.reference.list(episode.id, reference_type="character") == (
        references[0],
    )
    assert len(services.reference.list(episode.id)) == 4


def test_episode_reference_duplicate_and_remove_are_safe(services) -> None:
    item = services.information.create_information("秘密")
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "第一話")

    services.reference.add(episode.id, "information", item.id)
    with pytest.raises(RelationshipIntegrityError, match="RELATION_INTEGRITY_ERROR"):
        services.reference.add(episode.id, "information", item.id)
    assert services.reference.remove(episode.id, "information", item.id) is True
    assert services.reference.remove(episode.id, "information", item.id) is False


def test_episode_reference_rejects_invalid_role_and_unknown_type(services) -> None:
    character = services.character.create("主人公")
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "第一話")

    with pytest.raises(ValidationError, match="role"):
        services.reference.add(episode.id, "character", character.id, role="" * 1)
    with pytest.raises(ValidationError, match="reference_type"):
        services.reference.add(episode.id, "unknown", character.id)
