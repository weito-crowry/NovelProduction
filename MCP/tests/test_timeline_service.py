from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import (
    CanonReasonRequired,
    TimelineEventNotFoundError,
    VersionConflictError,
    WorkScopeError,
)
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.timeline_service import TimelineService


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
        yield TimelineService(connection)
    finally:
        connection.close()


def test_timeline_range_orders_events_and_relation_is_transactional(service):
    first = service.create_event("2104-01-01", "検知", participants=[])
    second = service.create_event("2104-02-01", "発表", participants=[])

    assert service.range_events("2104-01-01", "2104-12-31", limit=30) == (
        first,
        second,
    )
    relation = service.create_relation(first.id, second.id, "causes")
    assert relation.source_event_id == first.id


def test_timeline_event_maps_legacy_fields_and_participants(service):
    event = service.create_event(
        "2104-03-02",
        "  火山異常  ",
        participants=[("国家AI", "observer"), ("研究班", "announcer")],
    )

    assert event.title == "火山異常"
    assert event.chronology_sort_key == "2104-03-02"
    assert event.canon_status == "draft"
    assert event.participants == (("国家AI", "observer"), ("研究班", "announcer"))
    assert event.event_key
    assert service.search_events("山異", limit=10) == (event,)


def test_timeline_get_event_returns_record_and_stable_not_found(service):
    event = service.create_event("2104-03-02", "火山異常", participants=[])

    assert service.get_event(event.id) == event

    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        service.get_event(9999)


def test_timeline_update_and_move_require_expected_version(service):
    event = service.create_event("2104-01-01", "検知", participants=[])

    updated = service.update_event(
        event.id, event.version, title="発見", participants=[]
    )
    assert updated.title == "発見"
    assert updated.version == 2

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.move_event(event.id, event.version, "2104-01-02")

    moved = service.move_event(event.id, updated.version, "2104-01-02")
    assert moved.chronology_sort_key == "2104-01-02"
    assert moved.version == 3

    with pytest.raises(TimelineEventNotFoundError, match="NOT_FOUND"):
        service.update_event(9999, 1, title="存在しない")


def test_timeline_canonical_update_requires_reason_and_keeps_mirrors(service):
    event = service.create_event("2104-01-01", "旧題", participants=[])
    CanonService(service._connection).set_canon_status(
        "timeline_event", event.id, "canon", event.version, "採用"
    )

    with pytest.raises(CanonReasonRequired, match="CANON_REASON_REQUIRED"):
        service.update_event(event.id, 2, title="新題")

    updated = service.update_event(
        event.id, 2, title="新題", new_date="2104-02-01", reason="訂正理由"
    )

    assert updated.title == "新題"
    assert updated.chronology_sort_key == "2104-02-01"
    assert updated.version == 3
    assert service._connection.execute(
        "SELECT title, summary, chronology_sort_key FROM timeline_events WHERE id = ?",
        (event.id,),
    ).fetchone() == ("新題", "新題", "2104-02-01")
    assert service._connection.execute(
        """
        SELECT COUNT(*)
        FROM canon_decision_changes
        WHERE entity_type = 'timeline_event' AND entity_id = ?
        """,
        (event.id,),
    ).fetchone() == (2,)


def test_timeline_search_and_range_cap_limit_at_service_bound(service):
    for index in range(101):
        service.create_event("2104-01-01", f"検知 {index}", participants=[])

    assert len(service.search_events("検知", limit=1000)) == 100
    assert len(service.range_events("2104-01-01", "2104-01-01", limit=1000)) == 100


def test_timeline_range_is_inclusive_and_deterministic(service):
    first = service.create_event("2104-01-01", "同日後", participants=[])
    second = service.create_event("2104-01-01", "同日前", participants=[])
    outside = service.create_event("2104-01-02", "範囲外", participants=[])

    assert service.range_events("2104-01-01", "2104-01-01", limit=30) == (
        first,
        second,
    )
    assert outside not in service.range_events("2104-01-01", "2104-01-01", limit=30)


def test_timeline_rejects_self_and_duplicate_relations(service):
    first = service.create_event("2104-01-01", "検知", participants=[])
    second = service.create_event("2104-02-01", "発表", participants=[])
    service.create_relation(first.id, second.id, "causes")

    with pytest.raises(ValueError, match="self"):
        service.create_relation(first.id, first.id, "causes")
    with pytest.raises(ValueError, match="duplicate"):
        service.create_relation(first.id, second.id, "causes")


def test_timeline_relation_and_participant_mutation_is_scoped_to_work(
    service, tmp_path: Path
):
    event = service.create_event("2104-01-01", "検知", participants=[])
    connection = service._connection
    connection.execute(
        "INSERT INTO works (slug, title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    other_event_id = connection.execute(
        """
        INSERT INTO timeline_events (
            work_id, event_key, title, summary, chronology_sort_key, canon_status
        ) VALUES (?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (other_work_id, "other-event", "別", "別", "2104-01-02", "draft"),
    ).fetchone()[0]
    connection.commit()

    with pytest.raises(WorkScopeError, match="WORK_SCOPE_ERROR"):
        service.create_relation(event.id, other_event_id, "causes")
