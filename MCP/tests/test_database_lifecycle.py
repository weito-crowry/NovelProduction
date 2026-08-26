from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from novel_mcp.database import DatabaseConfig, open_database


def test_open_database_applies_connection_defaults_and_migrations(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(
        db_path=tmp_path / "story.db",
        migration_dir=Path(__file__).resolve().parents[1] / "migrations",
    )

    connection = open_database(config)

    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA busy_timeout").fetchone() == (5000,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchone() == ("001_initial.sql",)
    finally:
        connection.close()


def test_open_database_is_idempotent_for_existing_migrations(tmp_path: Path) -> None:
    config = DatabaseConfig(
        db_path=tmp_path / "story.db",
        migration_dir=Path(__file__).resolve().parents[1] / "migrations",
    )

    first_connection = open_database(config)
    first_connection.close()

    second_connection = open_database(config)

    try:
        assert second_connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            ("001_initial.sql",),
        ).fetchone() == (1,)
    finally:
        second_connection.close()


def test_open_database_rolls_back_failed_migrations(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_initial.sql").write_text(
        "CREATE TABLE schema_migrations "
        "(version TEXT PRIMARY KEY, checksum TEXT NOT NULL);\n"
        "CREATE TABLE seed_table (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    (migration_dir / "002_broken.sql").write_text(
        "CREATE TABLE should_not_exist (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO missing_table VALUES (1);\n",
        encoding="utf-8",
    )

    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=migration_dir)

    with pytest.raises(RuntimeError, match="002_broken.sql"):
        connection = open_database(config)
        connection.close()

    reopened = sqlite3.connect(config.db_path)

    try:
        tables = {
            row[0]
            for row in reopened.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "should_not_exist" not in tables
        assert reopened.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone() == (1,)
    finally:
        reopened.close()


def test_apply_migrations_rejects_changed_bytes_for_applied_filename(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "story.db"
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    migration_file = migration_dir / "001_initial.sql"
    migration_file.write_text(
        "CREATE TABLE schema_migrations "
        "(version TEXT PRIMARY KEY, checksum TEXT NOT NULL);\n",
        encoding="utf-8",
    )

    connection = open_database(
        DatabaseConfig(db_path=db_path, migration_dir=migration_dir)
    )
    connection.close()

    migration_file.write_text(
        "CREATE TABLE schema_migrations "
        "(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, changed INTEGER "
        "NOT NULL DEFAULT 0);\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="001_initial.sql"):
        open_database(DatabaseConfig(db_path=db_path, migration_dir=migration_dir))
