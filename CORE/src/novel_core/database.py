from __future__ import annotations

import logging
import sqlite3
from hashlib import sha256
from importlib import resources
from pathlib import Path

from novel_core.config import DatabaseConfig
from novel_core.errors import MigrationError

LOGGER = logging.getLogger(__name__)


def default_migration_dir() -> Path:
    checkout_dir = Path(__file__).resolve().parents[2] / "migrations"
    if checkout_dir.is_dir():
        return checkout_dir

    packaged_dir = resources.files("novel_core").joinpath("migrations")
    if not packaged_dir.is_dir():
        raise MigrationError("Packaged migrations are unavailable")
    if isinstance(packaged_dir, Path):
        return packaged_dir
    raise MigrationError("Packaged migrations are not available as filesystem paths")


def open_database(config: DatabaseConfig) -> sqlite3.Connection:
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.db_path)
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA busy_timeout = 5000;")
    try:
        apply_migrations(connection, config.migration_dir)
    except Exception:
        connection.close()
        raise
    return connection


def apply_migrations(
    connection: sqlite3.Connection, migration_dir: Path
) -> tuple[str, ...]:
    applied = _load_applied_migrations(connection)
    applied_versions: list[str] = []
    for migration_path in sorted(migration_dir.glob("*.sql")):
        checksum_candidates = _checksum_candidates_for_path(migration_path)
        checksum = checksum_candidates[1]
        existing_checksum = applied.get(migration_path.name)
        if existing_checksum is not None:
            if existing_checksum not in checksum_candidates:
                raise MigrationError(
                    f"Applied migration bytes changed for {migration_path.name}"
                )
            continue
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in _iter_statements(
                migration_path.read_text(encoding="utf-8")
            ):
                connection.execute(statement)
            _ensure_schema_migrations_table(connection)
            connection.execute(
                "INSERT INTO schema_migrations(version, checksum) VALUES (?, ?)",
                (migration_path.name, checksum),
            )
            connection.commit()
            applied_versions.append(migration_path.name)
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            LOGGER.exception("Failed to apply migration %s", migration_path.name)
            raise MigrationError(
                f"Failed to apply migration {migration_path.name}"
            ) from exc
    return tuple(applied_versions)


def _load_applied_migrations(connection: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(connection, "schema_migrations"):
        return {}
    rows = connection.execute(
        "SELECT version, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {version: checksum for version, checksum in rows}


def _ensure_schema_migrations_table(connection: sqlite3.Connection) -> None:
    if _table_exists(connection, "schema_migrations"):
        return
    raise MigrationError("Migration did not create schema_migrations")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _checksum_candidates_for_path(path: Path) -> tuple[str, str, str]:
    raw = path.read_bytes()
    canonical_lf = raw.replace(b"\r\n", b"\n")
    canonical_crlf = canonical_lf.replace(b"\n", b"\r\n")
    return (
        sha256(raw).hexdigest(),
        sha256(canonical_lf).hexdigest(),
        sha256(canonical_crlf).hexdigest(),
    )


def _iter_statements(script: str) -> tuple[str, ...]:
    statements: list[str] = []
    buffer: list[str] = []
    for line in script.splitlines():
        buffer.append(line)
        candidate = "\n".join(buffer).strip()
        if candidate and sqlite3.complete_statement(candidate):
            statements.append(candidate)
            buffer.clear()
    trailing = "\n".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return tuple(statements)
