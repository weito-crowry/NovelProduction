import sqlite3
from pathlib import Path

from novel_core.config import DatabaseConfig
from novel_core.database import open_database


MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"


def open_test_database(db_path: Path) -> sqlite3.Connection:
    return open_database(DatabaseConfig(db_path=db_path, migration_dir=MIGRATION_DIR))


def test_style_analysis_package_is_importable() -> None:
    import novel_core.style_analysis  # noqa: F401


def test_foundation_migration_is_present() -> None:
    assert (MIGRATION_DIR / "006_style_analysis_foundation.sql").is_file()
