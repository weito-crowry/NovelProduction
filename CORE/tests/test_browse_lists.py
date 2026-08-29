from __future__ import annotations

from pathlib import Path

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.repositories.character_repository import CharacterRepository
from novel_core.repositories.timeline_repository import TimelineRepository
from novel_core.repositories.work_repository import WorkRepository
from novel_core.repositories.world_fact_repository import WorldFactRepository
from novel_core.services.character_service import CharacterService
from novel_core.services.timeline_service import TimelineService
from novel_core.services.world_fact_service import WorldFactService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def connection(tmp_path: Path):
    connection = open_test_database(tmp_path / "story.db")
    initialize_test_work(connection, "Browse test")
    try:
        yield connection
    finally:
        connection.close()


def add_other_work(connection) -> int:
    repository = WorkRepository(connection)
    repository.begin_write()
    try:
        repository.create(
            slug="other",
            working_title="Other",
            genre="",
            premise="",
            themes_json="{}",
            description="",
            production_status="planned",
        )
        repository.commit()
    except Exception:
        repository.rollback()
        raise
    return connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]


def test_world_fact_list_orders_by_id_and_applies_limit_offset_and_work_scope(
    connection,
) -> None:
    service = WorldFactService(connection)
    first = service.create("first")
    second = service.create("second")
    third = service.create("third")
    other_work_id = add_other_work(connection)
    connection.execute(
        "INSERT INTO world_facts (work_id, topic_key, title, statement) "
        "VALUES (?, ?, ?, ?)",
        (other_work_id, "other", "other", "other"),
    )
    connection.commit()

    repository = WorldFactRepository(connection)
    assert repository.list(work_id=1, limit=2, offset=1) == (second, third)
    assert all(
        item.work_id == 1 for item in repository.list(work_id=1, limit=100, offset=0)
    )
    assert (
        repository.list(work_id=other_work_id, limit=100, offset=0)[0].work_id
        == other_work_id
    )
    assert (first, second, third) == repository.list(work_id=1, limit=100, offset=0)
    assert service.list(2, 1) == (second, third)


def test_character_list_orders_by_id_and_applies_limit_offset_and_work_scope(
    connection,
) -> None:
    service = CharacterService(connection)
    first = service.create("first")
    second = service.create("second")
    third = service.create("third")
    other_work_id = add_other_work(connection)
    connection.execute(
        "INSERT INTO characters (work_id, character_key, display_name) "
        "VALUES (?, ?, ?)",
        (other_work_id, "other", "other"),
    )
    connection.commit()

    repository = CharacterRepository(connection)
    assert repository.list(work_id=1, limit=2, offset=1) == (second, third)
    assert repository.list(work_id=1, limit=100, offset=0) == (
        first,
        second,
        third,
    )
    assert (
        repository.list(work_id=other_work_id, limit=100, offset=0)[0].work_id
        == other_work_id
    )
    assert service.list(2, 1) == (second, third)


def test_timeline_event_list_uses_chronology_null_last_tie_id_paging_and_hydration(
    connection,
) -> None:
    character = CharacterService(connection).create("participant")
    service = TimelineService(connection)
    later = service.create_event(
        "2104-02-01", "later", participants=[(character.id, "observer")]
    )
    tied_first = service.create_event("2104-01-01", "tied first")
    tied_second = service.create_event("2104-01-01", "tied second")
    unknown = service.create_event("正確な日付不明", "unknown")

    repository = TimelineRepository(connection)
    listed = repository.list_events(work_id=1, limit=100, offset=0)
    assert [event.id for event in listed] == [
        tied_first.id,
        tied_second.id,
        later.id,
        unknown.id,
    ]
    assert listed[0].participants == ()
    assert listed[2].participants[0].character_id == character.id
    assert [
        event.id for event in repository.list_events(work_id=1, limit=2, offset=1)
    ] == [
        tied_second.id,
        later.id,
    ]
    assert [event.id for event in service.list_events(2, 1)] == [
        tied_second.id,
        later.id,
    ]


def test_timeline_relation_list_filters_either_endpoint_and_scopes_work(
    connection,
) -> None:
    service = TimelineService(connection)
    first = service.create_event("2104-01-01", "first")
    second = service.create_event("2104-02-01", "second")
    third = service.create_event("2104-03-01", "third")
    first_relation = service.create_relation(first.id, second.id, "causes")
    second_relation = service.create_relation(third.id, first.id, "follows")
    other_work_id = add_other_work(connection)
    other_event_id = connection.execute(
        "INSERT INTO timeline_events (work_id, event_key, title) "
        "VALUES (?, ?, ?) RETURNING id",
        (other_work_id, "other", "other"),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO timeline_event_relations "
        "(work_id, source_event_id, target_event_id, relation_type) "
        "VALUES (?, ?, ?, ?)",
        (other_work_id, other_event_id, other_event_id, "other"),
    )
    connection.commit()

    repository = TimelineRepository(connection)
    assert repository.list_relations(work_id=1, event_id=None, limit=100, offset=0) == (
        first_relation,
        second_relation,
    )
    assert repository.list_relations(
        work_id=1, event_id=first.id, limit=100, offset=0
    ) == (
        first_relation,
        second_relation,
    )
    assert repository.list_relations(
        work_id=1, event_id=second.id, limit=100, offset=0
    ) == (first_relation,)
    assert (
        repository.list_relations(work_id=1, event_id=third.id, limit=1, offset=1) == ()
    )
    assert (
        repository.list_relations(
            work_id=other_work_id, event_id=None, limit=100, offset=0
        )[0].work_id
        == other_work_id
    )
    assert service.list_relations(first.id, 100, 0) == (
        first_relation,
        second_relation,
    )
