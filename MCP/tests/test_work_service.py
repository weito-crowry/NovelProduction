from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.work_service import WorkService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


def test_initialize_work_is_explicit_and_update_requires_version(
    tmp_path: Path,
) -> None:
    from novel_mcp.cli import initialize_work

    record = initialize_work(tmp_path / "story.db", "2126")

    assert record.working_title == "2126"
    assert record.version == 1

    connection = open_test_database(tmp_path / "story.db")
    try:
        service = WorkService(connection)
        updated = service.update(
            "2126 revised",
            expected_version=1,
            genre="SF",
            premise="A long premise",
            themes_json='["identity"]',
            description="A description",
            production_status="outlined",
        )
    finally:
        connection.close()

    assert updated.working_title == "2126 revised"
    assert (updated.genre, updated.premise, updated.themes_json) == (
        "SF",
        "A long premise",
        '["identity"]',
    )
    assert updated.description == "A description"
    assert updated.production_status == "outlined"
    assert updated.version == 2


def test_normal_open_does_not_create_a_work(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")

    try:
        assert WorkRepository(connection).get() is None
        assert connection.execute("SELECT COUNT(*) FROM works").fetchone() == (0,)
    finally:
        connection.close()


def test_service_get_raises_when_no_work_exists(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")

    try:
        with pytest.raises(RuntimeError, match="WORK_NOT_FOUND"):
            WorkService(connection).get()
    finally:
        connection.close()


def test_initialize_work_rejects_duplicate_initialization(tmp_path: Path) -> None:
    from novel_mcp.cli import initialize_work

    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")

    with pytest.raises(RuntimeError, match="WORK_EXISTS"):
        initialize_work(db_path, "second title")


def test_update_rejects_stale_version_and_empty_title(tmp_path: Path) -> None:
    from novel_mcp.cli import initialize_work

    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)

    try:
        service = WorkService(connection)
        with pytest.raises(RuntimeError, match="VERSION_CONFLICT"):
            service.update("2126 revised", expected_version=999)
        with pytest.raises(ValueError, match="title"):
            service.update("   ", expected_version=1)
    finally:
        connection.close()


def test_work_repository_update_does_not_commit_service_owned_transaction(
    tmp_path: Path,
) -> None:
    from novel_mcp.cli import initialize_work

    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)

    try:
        repository = WorkRepository(connection)
        repository.begin_write()
        updated = repository.update(
            expected_version=1, fields={"working_title": "uncommitted"}
        )

        assert updated.working_title == "uncommitted"
        assert connection.in_transaction is True
        repository.rollback()
        assert repository.get().working_title == "2126"
    finally:
        connection.close()


def test_work_service_rejects_invalid_themes_and_status(tmp_path: Path) -> None:
    from novel_mcp.cli import initialize_work

    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)

    try:
        service = WorkService(connection)
        with pytest.raises(ValueError, match="themes_json"):
            service.update("2126", expected_version=1, themes_json="not-json")
        with pytest.raises(ValueError, match="production_status"):
            service.update("2126", expected_version=1, production_status="unknown")
    finally:
        connection.close()
