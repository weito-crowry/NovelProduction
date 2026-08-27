from __future__ import annotations

from pathlib import Path

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import (
    CanonReasonRequired,
    TimelineEventNotFoundError,
    VersionConflictError,
    WorkScopeError,
)
from novel_core.services.canon_service import CanonService
from novel_core.services.character_service import CharacterService
from novel_core.services.timeline_service import TimelineService


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
        yield TimelineService(connection)
    finally:
        connection.close()


def test_timeline_range_orders_events_and_relation_is_transactional(
    service: TimelineService,
) -> None:
    first = service.create_event("2104-01-01", "検知")
    second = service.create_event("2104-02-01", "発表")
    assert service.range_events("2104-01-01", "2104-12-31", 30) == (first, second)
    relation = service.create_relation(first.id, second.id, "causes")
    assert relation.source_event_id == first.id


def test_timeline_supports_year_season_month_unknown_and_character_fk(
    service: TimelineService,
) -> None:
    character = CharacterService(service._connection).create("国家AI", entity_type="ai")
    event = service.create_event(
        "2104年春頃",
        "火山異常",
        description="記録",
        category="history",
        participants=[(character.id, "observer")],
    )
    assert (
        event.time_start,
        event.time_end,
        event.date_precision,
        event.date_display,
    ) == ("2104-03-01", "2104-05-31", "season", "2104年春頃")
    assert event.participants[0].character_id == character.id
    assert event.participants[0].role == "observer"
    year = service.create_event("2105年", "年次")
    month = service.create_event("2106年3月頃", "月次")
    unknown = service.create_event("正確な日付不明", "不明")
    assert (year.date_precision, year.time_start, year.time_end) == (
        "year",
        "2105-01-01",
        "2105-12-31",
    )
    assert (month.date_precision, month.time_start, month.time_end) == (
        "month",
        "2106-03-01",
        "2106-03-31",
    )
    assert (unknown.date_precision, unknown.time_start, unknown.time_end) == (
        "unknown",
        None,
        None,
    )
    winter = service.create_event("2103年冬頃", "うるう年をまたぐ冬")
    assert (
        winter.time_start,
        winter.time_end,
        winter.date_precision,
        winter.date_display,
    ) == ("2103-12-01", "2104-02-29", "season", "2103年冬頃")


def test_timeline_get_event_returns_record_and_stable_not_found(
    service: TimelineService,
) -> None:
    event = service.create_event("2104-03-02", "火山異常")
    assert service.get_event(event.id) == event
    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        service.get_event(9999)


def test_timeline_update_and_move_require_expected_version(
    service: TimelineService,
) -> None:
    event = service.create_event("2104-01-01", "検知")
    updated = service.update_event(event.id, event.version, title="発見")
    assert (updated.title, updated.version) == ("発見", 2)
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.move_event(event.id, event.version, "2104-01-02")
    moved = service.move_event(event.id, updated.version, "2104-01-02")
    assert (moved.time_start, moved.time_end, moved.date_precision, moved.version) == (
        "2104-01-02",
        "2104-01-02",
        "day",
        3,
    )
    with pytest.raises(TimelineEventNotFoundError, match="NOT_FOUND"):
        service.update_event(9999, 1, title="存在しない")


def test_timeline_canonical_update_requires_reason(service: TimelineService) -> None:
    event = service.create_event("2104-01-01", "旧題")
    CanonService(service._connection).set_canon_status(
        "timeline_event", event.id, "canon", event.version, "採用"
    )
    with pytest.raises(CanonReasonRequired, match="CANON_REASON_REQUIRED"):
        service.update_event(event.id, 2, title="新題")
    updated = service.update_event(
        event.id, 2, title="新題", new_date="2104-02-01", reason="訂正理由"
    )
    assert (updated.title, updated.time_start, updated.version) == (
        "新題",
        "2104-02-01",
        3,
    )
    assert service._connection.execute(
        "SELECT title, description, time_start, time_end "
        "FROM timeline_events WHERE id = ?",
        (event.id,),
    ).fetchone() == ("新題", "", "2104-02-01", "2104-02-01")


def test_timeline_search_and_range_cap_limit_at_service_bound(
    service: TimelineService,
) -> None:
    for index in range(101):
        service.create_event("2104-01-01", f"検知 {index}")
    assert len(service.search_events("検知", 1000)) == 100
    assert len(service.range_events("2104-01-01", "2104-01-01", 1000)) == 100


def test_timeline_range_is_inclusive_and_deterministic(
    service: TimelineService,
) -> None:
    first = service.create_event("2104-01-01", "同日後")
    second = service.create_event("2104-01-01", "同日前")
    outside = service.create_event("2104-01-02", "範囲外")
    assert service.range_events("2104-01-01", "2104-01-01", 30) == (first, second)
    assert outside not in service.range_events("2104-01-01", "2104-01-01", 30)


def test_timeline_rejects_self_and_duplicate_relations(
    service: TimelineService,
) -> None:
    first = service.create_event("2104-01-01", "検知")
    second = service.create_event("2104-02-01", "発表")
    service.create_relation(first.id, second.id, "causes")
    with pytest.raises(ValueError, match="self"):
        service.create_relation(first.id, first.id, "causes")
    with pytest.raises(ValueError, match="duplicate"):
        service.create_relation(first.id, second.id, "causes")


def test_timeline_location_and_participants_are_work_scoped(
    service: TimelineService,
) -> None:
    event = service.create_event("2104-01-01", "検知")
    connection = service._connection
    connection.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    other_event_id = connection.execute(
        """
        INSERT INTO timeline_events
            (work_id, event_key, time_start, time_end, date_precision,
             date_display, title)
        VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id
        """,
        (
            other_work_id,
            "other-event",
            "2104-01-02",
            "2104-01-02",
            "day",
            "2104-01-02",
            "別",
        ),
    ).fetchone()[0]
    other_fact_id = connection.execute(
        """
        INSERT INTO world_facts
            (work_id, topic_key, category, title, statement, details_json)
        VALUES (?, ?, ?, ?, ?, ?) RETURNING id
        """,
        (other_work_id, "other-fact", "history", "別", "別", "{}"),
    ).fetchone()[0]
    connection.commit()
    with pytest.raises(WorkScopeError, match="WORK_SCOPE_ERROR"):
        service.create_relation(event.id, other_event_id, "causes")
    with pytest.raises(WorkScopeError, match="WORK_SCOPE_ERROR"):
        service.update_event(
            event.id, event.version, location_world_fact_id=other_fact_id
        )
