from __future__ import annotations

from pathlib import Path

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import ValidationError, VersionConflictError
from novel_core.services.canon_service import CanonService
from novel_core.services.disclosure_service import DisclosureService
from novel_core.services.information_service import InformationService
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
    db_path = tmp_path / "story.db"
    connection = open_test_database(db_path)
    try:
        initialize_test_work(connection, "2126")
        yield type(
            "Services",
            (),
            {
                "connection": connection,
                "information": InformationService(connection),
                "narrative": NarrativeService(connection),
                "disclosure": DisclosureService(connection),
            },
        )()
    finally:
        connection.close()


def test_reader_disclosure_is_a_first_narrative_boundary(services) -> None:
    item = services.information.create_information("秘密")
    chapter = services.narrative.create_chapter("章")
    episodes = [
        services.narrative.create_episode(chapter.id, f"話{i}") for i in range(1, 4)
    ]

    disclosure = services.disclosure.set_reader_disclosure(
        item.id, episodes[1].id, expected_version=None
    )

    assert disclosure.episode_id == episodes[1].id
    assert services.disclosure.known_before(item.id, episodes[1].id) == ()
    assert services.disclosure.reveal_this_episode(item.id, episodes[1].id) == (item,)
    assert services.disclosure.known_before(item.id, episodes[2].id) == (item,)


def test_reader_disclosure_move_requires_current_version(services) -> None:
    item = services.information.create_information("秘密")
    chapter = services.narrative.create_chapter("章")
    first = services.narrative.create_episode(chapter.id, "第一話")
    second = services.narrative.create_episode(chapter.id, "第二話")
    disclosure = services.disclosure.set_reader_disclosure(
        item.id, first.id, expected_version=None
    )

    with pytest.raises(ValidationError, match="expected_version"):
        services.disclosure.set_reader_disclosure(item.id, second.id)
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        services.disclosure.set_reader_disclosure(
            item.id, second.id, expected_version=999
        )
    moved = services.disclosure.set_reader_disclosure(
        item.id, second.id, expected_version=disclosure.version
    )
    assert (moved.episode_id, moved.version) == (second.id, 2)


def test_deprecated_information_is_excluded_from_boundary_reads(services) -> None:
    item = services.information.create_information("撤回情報")
    chapter = services.narrative.create_chapter("章")
    first = services.narrative.create_episode(chapter.id, "第一話")
    second = services.narrative.create_episode(chapter.id, "第二話")
    services.disclosure.set_reader_disclosure(item.id, first.id, expected_version=None)

    canon = CanonService(services.connection)
    canon.set_canon_status("information_item", item.id, "canon", 1, "採用")
    canon.set_canon_status("information_item", item.id, "deprecated", 2, "撤回")

    assert services.disclosure.known_before(item.id, second.id) == ()
    assert services.disclosure.reveal_this_episode(item.id, first.id) == ()
