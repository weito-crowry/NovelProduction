import shutil
import sqlite3
from pathlib import Path

from novel_core.config import DatabaseConfig
from novel_core.database import open_database

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"
EXPECTED_LEGACY_MIGRATIONS = tuple(
    sorted(path.name for path in MIGRATION_DIR.glob("00[1-5]_*.sql"))
)
FOUNDATION_MIGRATION = "006_style_analysis_foundation.sql"
FOUNDATION_TABLES = (
    "style_jobs",
    "style_sources",
    "style_source_snapshots",
    "style_reference_works",
    "style_reference_episodes",
    "style_documents",
    "style_text_revisions",
    "style_text_mappings",
    "style_structure_revisions",
    "style_scenes",
    "style_blocks",
    "style_sentences",
    "style_analysis_runs",
    "style_analysis_run_dependencies",
    "style_structure_analysis_sources",
)


def open_test_database(db_path: Path) -> sqlite3.Connection:
    return open_database(DatabaseConfig(db_path=db_path, migration_dir=MIGRATION_DIR))


def copy_migrations(source: Path, destination: Path, names: tuple[str, ...]) -> None:
    destination.mkdir()
    for name in names:
        shutil.copyfile(source / name, destination / name)


def test_style_analysis_package_is_importable() -> None:
    import novel_core.style_analysis  # noqa: F401


def test_foundation_migration_is_present() -> None:
    assert (MIGRATION_DIR / FOUNDATION_MIGRATION).is_file()


def test_legacy_migration_bytes_remain_unchanged(tmp_path: Path) -> None:
    before = {
        name: (MIGRATION_DIR / name).read_bytes() for name in EXPECTED_LEGACY_MIGRATIONS
    }

    connection = open_test_database(tmp_path / "story.db")
    try:
        applied = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        assert applied == tuple(
            sorted((*EXPECTED_LEGACY_MIGRATIONS, FOUNDATION_MIGRATION))
        )
    finally:
        connection.close()

    assert {
        name: (MIGRATION_DIR / name).read_bytes() for name in EXPECTED_LEGACY_MIGRATIONS
    } == before


def test_foundation_schema_supports_fresh_and_existing_databases(
    tmp_path: Path,
) -> None:
    fresh = open_test_database(tmp_path / "fresh.db")

    legacy_dir = tmp_path / "legacy-migrations"
    copy_migrations(MIGRATION_DIR, legacy_dir, EXPECTED_LEGACY_MIGRATIONS)
    legacy_path = tmp_path / "legacy.db"
    legacy = open_database(
        DatabaseConfig(db_path=legacy_path, migration_dir=legacy_dir)
    )
    legacy.close()

    upgraded_dir = tmp_path / "upgraded-migrations"
    copy_migrations(
        MIGRATION_DIR,
        upgraded_dir,
        (*EXPECTED_LEGACY_MIGRATIONS, FOUNDATION_MIGRATION),
    )
    upgraded = open_database(
        DatabaseConfig(db_path=legacy_path, migration_dir=upgraded_dir)
    )

    try:
        for connection in (fresh, upgraded):
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert (
                tuple(
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name LIKE 'style_%' "
                        "ORDER BY rowid"
                    )
                )
                == FOUNDATION_TABLES
            )
    finally:
        fresh.close()
        upgraded.close()
