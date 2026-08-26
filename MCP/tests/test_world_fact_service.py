from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import VersionConflictError
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


def test_world_fact_create_persists_statement_and_temporal_bounds(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)

    try:
        service = WorldFactService(connection)
        created = service.create(
            "火山異常は2104年に検知された",
            "2104-01-01",
            "2104-12-31",
        )

        fetched = service.get(created.id)

        assert fetched == created
        assert fetched.statement == "火山異常は2104年に検知された"
        assert fetched.valid_from == "2104-01-01"
        assert fetched.valid_to == "2104-12-31"
        assert fetched.version == 1
        assert connection.execute(
            """
            SELECT title, body, canon_status, valid_from, valid_to
            FROM world_facts
            WHERE id = ?
            """,
            (created.id,),
        ).fetchone() == (
            "火山異常は2104年に検知された",
            "火山異常は2104年に検知された",
            "draft",
            "2104-01-01",
            "2104-12-31",
        )
    finally:
        connection.close()


def test_world_fact_create_rejects_invalid_temporal_bounds(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)

    try:
        with pytest.raises(ValueError, match="valid_to"):
            WorldFactService(connection).create(
                "火山異常は2104年に検知された",
                "2104-12-31",
                "2104-01-01",
            )
    finally:
        connection.close()


def test_world_fact_update_rejects_stale_version_and_missing_fact(
    initialized_db_path: Path,
) -> None:
    connection = open_test_database(initialized_db_path)

    try:
        service = WorldFactService(connection)
        fact = service.create("火山異常は2104年に検知された", None, None)

        with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
            service.update(fact.id, "変更", expected_version=0)

        with pytest.raises(RuntimeError, match="NOT_FOUND"):
            service.update(9999, "変更", expected_version=1)
    finally:
        connection.close()


def test_world_fact_search_is_scoped_and_deterministic(
    initialized_db_path: Path,
) -> None:
    primary_connection = open_test_database(initialized_db_path)

    try:
        primary_service = WorldFactService(primary_connection)
        first = primary_service.create("国家AIが火山異常を検知", None, None)
        second = primary_service.create("火山異常は翌日に公表された", None, None)

        primary_connection.execute(
            """
            INSERT INTO works (slug, title, description)
            VALUES (?, ?, NULL)
            """,
            ("other", "other"),
        )
        other_work_id = primary_connection.execute(
            "SELECT id FROM works WHERE slug = ?",
            ("other",),
        ).fetchone()[0]
        primary_connection.execute(
            """
            INSERT INTO world_facts (
                work_id,
                fact_key,
                title,
                body,
                canon_status,
                valid_from,
                valid_to
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                other_work_id,
                "other-fact",
                "別作品でも火山異常が話題になった",
                "別作品でも火山異常が話題になった",
                "draft",
                None,
                None,
            ),
        )
        primary_connection.commit()
        other_fact_id = primary_connection.execute(
            """
            SELECT id
            FROM world_facts
            WHERE work_id = ? AND fact_key = ?
            """,
            (other_work_id, "other-fact"),
        ).fetchone()[0]

        assert primary_service.search("火山異常", limit=10) == (first, second)
        assert primary_service.search("不存在", limit=10) == ()
        with pytest.raises(RuntimeError, match="NOT_FOUND"):
            primary_service.get(other_fact_id)
    finally:
        primary_connection.close()
