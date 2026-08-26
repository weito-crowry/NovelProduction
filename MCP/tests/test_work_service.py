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

    assert record.title == "2126"
    assert record.version == 1

    service = WorkService(open_test_database(tmp_path / "story.db"))
    updated = service.update("2126 revised", expected_version=1)

    assert updated.title == "2126 revised"
    assert updated.version == 2


def test_normal_open_does_not_create_a_work(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")

    try:
        assert WorkRepository(connection).get() is None
        assert (
            connection.execute("SELECT COUNT(*) FROM works").fetchone()
            == (0,)
        )
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
