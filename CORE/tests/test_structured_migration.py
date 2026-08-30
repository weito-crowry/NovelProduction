from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from novel_core.config import DatabaseConfig
from novel_core.database import assert_database_integrity, open_database

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"
LEGACY_MIGRATIONS = (
    "001_initial.sql",
    "002_search.sql",
    "003_narrative.sql",
    "004_drafts.sql",
)
ALL_MIGRATIONS = (*LEGACY_MIGRATIONS, "005_structured_drafts.sql")


def _copy_migrations(source: Path, destination: Path, names: tuple[str, ...]) -> Path:
    destination.mkdir()
    for name in names:
        shutil.copyfile(source / name, destination / name)
    return destination


def _open(path: Path, migration_dir: Path) -> sqlite3.Connection:
    return open_database(DatabaseConfig(db_path=path, migration_dir=migration_dir))


def _create_legacy_database(tmp_path: Path) -> tuple[Path, Path]:
    legacy_dir = _copy_migrations(
        MIGRATION_DIR, tmp_path / "legacy-migrations", LEGACY_MIGRATIONS
    )
    db_path = tmp_path / "legacy.db"
    connection = _open(db_path, legacy_dir)
    connection.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)", ("main", "Legacy")
    )
    work_id = connection.execute("SELECT id FROM works").fetchone()[0]
    connection.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, ?, ?)",
        (work_id, 1, "Chapter"),
    )
    chapter_id = connection.execute("SELECT id FROM chapters").fetchone()[0]
    connection.execute(
        "INSERT INTO episodes "
        "(work_id, chapter_id, position, title) VALUES (?, ?, ?, ?)",
        (work_id, chapter_id, 1, "Episode"),
    )
    episode_id = connection.execute("SELECT id FROM episodes").fetchone()[0]
    parent_id: int | None = None
    for revision in range(1, 4):
        cursor = connection.execute(
            """
            INSERT INTO drafts
                (work_id, episode_id, revision, parent_draft_id, body, content_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (work_id, episode_id, revision, parent_id, f"r{revision}", "a" * 64),
        )
        parent_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return db_path, legacy_dir


def test_fresh_database_applies_exactly_migrations_001_to_005(tmp_path: Path) -> None:
    connection = _open(tmp_path / "fresh.db", MIGRATION_DIR)
    try:
        assert (
            tuple(
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            )
            == ALL_MIGRATIONS
        )
        assert_database_integrity(connection)
    finally:
        connection.close()


def test_populated_legacy_drafts_are_replaced_without_disabling_foreign_keys(
    tmp_path: Path,
) -> None:
    db_path, _ = _create_legacy_database(tmp_path)

    connection = _open(db_path, MIGRATION_DIR)
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM drafts").fetchone() == (0,)
        assert (
            tuple(
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            )
            == ALL_MIGRATIONS
        )

        columns = {row[1] for row in connection.execute("PRAGMA table_info(drafts)")}
        assert columns == {
            "id",
            "work_id",
            "episode_id",
            "revision",
            "parent_draft_id",
            "document_json",
            "source_agent",
            "change_summary",
            "created_at",
        }

        indexes = {
            row[1]: tuple(
                item[2] for item in connection.execute(f"PRAGMA index_info('{row[1]}')")
            )
            for row in connection.execute("PRAGMA index_list(drafts)")
            if row[2]
        }
        assert set(indexes.values()) >= {
            ("work_id", "id"),
            ("episode_id", "revision"),
            ("work_id", "episode_id", "id"),
        }
        assert ("episode_id", "revision") in set(indexes.values())

        foreign_keys = tuple(connection.execute("PRAGMA foreign_key_list(drafts)"))
        assert {
            (row[2], row[3], row[4], row[6])
            for row in foreign_keys
            if row[2] == "episodes"
        } == {
            ("episodes", "work_id", "work_id", "CASCADE"),
            ("episodes", "episode_id", "id", "CASCADE"),
        }
        assert {
            (row[2], row[3], row[4], row[6])
            for row in foreign_keys
            if row[2] == "drafts"
        } == {
            ("drafts", "work_id", "work_id", "RESTRICT"),
            ("drafts", "episode_id", "episode_id", "RESTRICT"),
            ("drafts", "parent_draft_id", "id", "RESTRICT"),
        }

        work_id, episode_id = connection.execute(
            "SELECT work_id, id FROM episodes"
        ).fetchone()
        connection.execute(
            "INSERT INTO drafts (work_id, episode_id, revision, document_json) "
            "VALUES (?, ?, ?, ?)",
            (
                work_id,
                episode_id,
                1,
                '{"schema_version":1,"type":"novel_document","blocks":[]}',
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE drafts SET document_json = ? WHERE id = 1", ('{"x": 1}',)
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM drafts WHERE id = 1")
        connection.rollback()
        assert_database_integrity(connection)
    finally:
        connection.close()


def test_structured_migration_has_required_order_and_foreign_key_guard() -> None:
    source = (MIGRATION_DIR / "005_structured_drafts.sql").read_text(encoding="utf-8")
    statements = [statement.strip().upper() for statement in source.split(";")]
    required = (
        "DROP TRIGGER DRAFTS_APPEND_ONLY_UPDATE",
        "DROP TRIGGER DRAFTS_APPEND_ONLY_DELETE",
        "UPDATE DRAFTS SET PARENT_DRAFT_ID = NULL",
        "DELETE FROM DRAFTS",
        "DROP TABLE DRAFTS",
        "CREATE TABLE DRAFTS",
        "CREATE INDEX IDX_DRAFTS_EPISODE_REVISION",
        "CREATE TRIGGER DRAFTS_APPEND_ONLY_UPDATE",
        "CREATE TRIGGER DRAFTS_APPEND_ONLY_DELETE",
    )
    positions = [
        next(i for i, statement in enumerate(statements) if statement.startswith(item))
        for item in required
    ]
    assert positions == sorted(positions)
    assert "PRAGMA FOREIGN_KEYS = OFF" not in source.upper()
