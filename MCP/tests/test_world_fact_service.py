from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import CanonReasonRequired, VersionConflictError
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.world_fact_service import WorldFactService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def initialized_db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    return db_path


def test_world_fact_create_persists_normalized_fields(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)
    try:
        created = WorldFactService(connection).create(
            "火山異常は2104年に検知された",
            "2104-01-01",
            "2104-12-31",
            topic_key="volcanic-anomaly",
            category="history",
            title="火山異常",
            details_json='{"source":"archive"}',
            importance=4,
        )
        assert created == WorldFactService(connection).get(created.id)
        assert (created.topic_key, created.category, created.title) == (
            "volcanic-anomaly",
            "history",
            "火山異常",
        )
        assert created.statement.endswith("検知された")
        assert created.details_json == '{"source":"archive"}'
        assert created.importance == 4
        assert connection.execute(
            "SELECT title, statement, canon_status, version "
            "FROM world_facts WHERE id = ?",
            (created.id,),
        ).fetchone() == ("火山異常", "火山異常は2104年に検知された", "draft", 1)
    finally:
        connection.close()


def test_world_fact_create_rejects_invalid_temporal_bounds(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)
    try:
        with pytest.raises(ValueError, match="valid_to"):
            WorldFactService(connection).create("火山異常", "2104-12-31", "2104-01-01")
    finally:
        connection.close()


def test_world_fact_update_rejects_stale_version_and_missing_fact(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)
    try:
        service = WorldFactService(connection)
        fact = service.create("火山異常")
        with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
            service.update(fact.id, "変更", expected_version=0)
        with pytest.raises(RuntimeError, match="NOT_FOUND"):
            service.update(9999, "変更", expected_version=1)
    finally:
        connection.close()


def test_world_fact_search_is_scoped_and_deterministic(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)
    try:
        service = WorldFactService(connection)
        first = service.create("国家AIが火山異常を検知")
        second = service.create("火山異常は翌日に公表された")
        connection.execute(
            "INSERT INTO works (slug, title) VALUES (?, ?)", ("other", "other")
        )
        other_work_id = connection.execute(
            "SELECT id FROM works WHERE slug = ?", ("other",)
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO world_facts
                (work_id, topic_key, category, title, statement, details_json,
                 canon_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                other_work_id,
                "other-fact",
                "history",
                "別作品",
                "別作品の火山異常",
                "{}",
                "draft",
            ),
        )
        connection.commit()
        other_fact_id = connection.execute(
            "SELECT id FROM world_facts WHERE work_id = ?", (other_work_id,)
        ).fetchone()[0]
        assert service.search("火山異常", 10) == (first, second)
        assert service.search("不存在", 10) == ()
        with pytest.raises(RuntimeError, match="NOT_FOUND"):
            service.get(other_fact_id)
    finally:
        connection.close()


def test_world_fact_canon_edit_requires_reason_but_draft_edit_is_not_decision(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)
    try:
        service = WorldFactService(connection)
        fact = service.create("旧記述")
        draft_edit = service.update(fact.id, "通常編集", expected_version=1)
        assert draft_edit.version == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM canon_decisions"
        ).fetchone() == (0,)
        CanonService(connection).set_canon_status(
            "world_fact", fact.id, "canon", 2, "採用"
        )
        with pytest.raises(CanonReasonRequired, match="CANON_REASON_REQUIRED"):
            service.update(fact.id, "新記述", expected_version=3)
        updated = service.update(
            fact.id, "新記述", expected_version=3, reason="訂正理由"
        )
        assert updated.statement == "新記述"
        assert updated.version == 4
        assert connection.execute(
            "SELECT COUNT(*) FROM canon_decisions"
        ).fetchone() == (2,)
    finally:
        connection.close()


def test_world_fact_search_caps_limit_at_service_bound(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)
    try:
        service = WorldFactService(connection)
        for index in range(101):
            service.create(f"火山異常 {index}")
        assert len(service.search("火山異常", 1000)) == 100
        assert service.search("火山異常", 0) == ()
    finally:
        connection.close()
