from __future__ import annotations

from pathlib import Path

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.repositories.canon_repository import CanonChange
from novel_core.services.canon_service import CanonService
from novel_core.services.character_service import CharacterService
from novel_core.services.disclosure_service import DisclosureService
from novel_core.services.information_service import InformationService
from novel_core.services.knowledge_service import KnowledgeService
from novel_core.services.narrative_service import NarrativeService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def services(tmp_path: Path):
    connection = open_test_database(tmp_path / "story.db")
    initialize_test_work(connection, "D4 reads")
    try:
        yield type(
            "Services",
            (),
            {
                "connection": connection,
                "canon": CanonService(connection),
                "character": CharacterService(connection),
                "disclosure": DisclosureService(connection),
                "information": InformationService(connection),
                "knowledge": KnowledgeService(connection),
                "narrative": NarrativeService(connection),
            },
        )()
    finally:
        connection.close()


def test_information_list_is_id_ordered_and_paged(services) -> None:
    records = [
        services.information.create_information(f"Information {index}")
        for index in range(3)
    ]

    assert services.information.list(2, 1) == tuple(records[1:])
    assert services.information.list(2, 3) == ()


def test_canon_decision_list_is_id_ordered_and_paged(services) -> None:
    item = services.information.create_information("Canon target")
    change = CanonChange(
        entity_type="information_item",
        entity_id=item.id,
        action="annotated",
        before_payload={"statement": "old"},
        after_payload={"statement": "new"},
    )
    decisions = [
        services.canon.record_decision(f"Decision {index}", "reason", (change,))
        for index in range(3)
    ]

    assert services.canon.list_decisions(2, 1) == tuple(decisions[1:])
    assert services.canon.list_decisions(2, 3) == ()


def test_reader_disclosure_read_returns_record_or_none(services) -> None:
    item = services.information.create_information("Disclosure")
    chapter = services.narrative.create_chapter("Chapter")
    episode = services.narrative.create_episode(chapter.id, "Episode")

    assert services.disclosure.get_reader_disclosure(item.id) is None
    expected = services.disclosure.set_reader_disclosure(
        item.id, episode.id, expected_version=None
    )

    assert services.disclosure.get_reader_disclosure(item.id) == expected


def test_exact_knowledge_read_does_not_project_prior_event(services) -> None:
    character = services.character.create("reader")
    item = services.information.create_information("Secret")
    chapter = services.narrative.create_chapter("Chapter")
    first = services.narrative.create_episode(chapter.id, "First")
    second = services.narrative.create_episode(chapter.id, "Second")
    prior = services.knowledge.set_character_knowledge(
        character.id,
        item.id,
        first.id,
        "believes",
        "prior note",
        expected_version=None,
    )

    effective = services.knowledge.get_character_knowledge(character.id, second.id)
    assert effective[0].event_id == prior.id
    assert (
        services.knowledge.get_character_knowledge_event(
            character.id, item.id, second.id
        )
        is None
    )

    exact = services.knowledge.set_character_knowledge(
        character.id,
        item.id,
        second.id,
        "knows",
        "exact note",
        expected_version=None,
    )
    assert (
        services.knowledge.get_character_knowledge_event(
            character.id, item.id, second.id
        )
        == exact
    )
