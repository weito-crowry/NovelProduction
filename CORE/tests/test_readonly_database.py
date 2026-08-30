from __future__ import annotations

import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest

import novel_core.database as database_module
from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import MigrationError

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATION_NAMES = (
    "001_initial.sql",
    "002_search.sql",
    "003_narrative.sql",
    "004_drafts.sql",
    "005_structured_drafts.sql",
)


def test_open_database_readonly_reads_without_enabling_write_pragmas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    writer = open_database(config)
    writer.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("main", "Read only"),
    )
    writer.commit()
    writer.close()

    calls: list[tuple[object, ...]] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        calls.append((*args, *kwargs.values()))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    connection = database_module.open_database_readonly(config)
    try:
        assert connection.execute("SELECT working_title FROM works").fetchone() == (
            "Read only",
        )
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA busy_timeout").fetchone() == (5000,)
        assert len(calls) == 1
        assert calls[0][0] == f"{config.db_path.resolve().as_uri()}?mode=ro"
        assert calls[0][-1] is True
        assert "immutable=1" not in str(calls[0][0])
    finally:
        connection.close()


def test_open_database_readonly_rejects_main_database_writes(tmp_path: Path) -> None:
    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    writer = open_database(config)
    writer.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("main", "Read only"),
    )
    writer.commit()
    writer.close()

    connection = database_module.open_database_readonly(config)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute(
                "INSERT INTO works (slug, working_title) VALUES (?, ?)",
                ("write", "must fail"),
            )
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("UPDATE works SET working_title = 'changed'")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE should_not_exist (id INTEGER)")
    finally:
        connection.close()


def test_open_database_readonly_does_not_create_missing_parent_or_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing" / "story.db"

    with pytest.raises(sqlite3.OperationalError):
        database_module.open_database_readonly(
            DatabaseConfig(db_path=db_path, migration_dir=MIGRATION_DIR)
        )

    assert not db_path.parent.exists()
    assert not db_path.exists()


def test_open_database_readonly_fails_closed_without_applying_migrations(
    tmp_path: Path,
) -> None:
    partial_dir = tmp_path / "partial-migrations"
    partial_dir.mkdir()
    for name in MIGRATION_NAMES[:3]:
        (partial_dir / name).write_bytes((MIGRATION_DIR / name).read_bytes())
    db_path = tmp_path / "story.db"
    open_database(DatabaseConfig(db_path=db_path, migration_dir=partial_dir)).close()

    with pytest.raises(MigrationError, match="004_drafts.sql"):
        database_module.open_database_readonly(
            DatabaseConfig(db_path=db_path, migration_dir=MIGRATION_DIR)
        )

    verification = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        assert tuple(
            verification.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ) == tuple((name,) for name in MIGRATION_NAMES[:3])
    finally:
        verification.close()


def test_open_database_readonly_rejects_changed_migration_bytes(
    tmp_path: Path,
) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    for name in MIGRATION_NAMES:
        (migration_dir / name).write_bytes((MIGRATION_DIR / name).read_bytes())
    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=migration_dir)
    connection = open_database(config)
    connection.close()

    changed_path = migration_dir / "002_search.sql"
    changed_path.write_bytes(changed_path.read_bytes() + b"\n-- changed\n")
    before = sha256(config.db_path.read_bytes()).hexdigest()

    with pytest.raises(MigrationError, match="002_search.sql"):
        database_module.open_database_readonly(config)

    assert sha256(config.db_path.read_bytes()).hexdigest() == before


def test_open_database_readonly_preserves_database_hash(tmp_path: Path) -> None:
    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    connection = open_database(config)
    connection.close()
    before = sha256(config.db_path.read_bytes()).hexdigest()

    readonly = database_module.open_database_readonly(config)
    try:
        readonly.execute("SELECT COUNT(*) FROM works").fetchone()
    finally:
        readonly.close()

    assert sha256(config.db_path.read_bytes()).hexdigest() == before


def test_open_database_readonly_allows_empty_runtime_sidecars_after_quiescence(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    writer = open_database(config)
    assert writer.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    writer.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("main", "Quiescent read only"),
    )
    writer.commit()
    writer.close()

    wal_path = Path(f"{config.db_path}-wal")
    shm_path = Path(f"{config.db_path}-shm")
    assert not wal_path.exists()
    assert not shm_path.exists()
    before = (
        sha256(config.db_path.read_bytes()).hexdigest(),
        config.db_path.stat().st_size,
    )

    readonly = database_module.open_database_readonly(config)
    try:
        assert readonly.execute("SELECT working_title FROM works").fetchone() == (
            "Quiescent read only",
        )
    finally:
        readonly.close()

    assert (
        sha256(config.db_path.read_bytes()).hexdigest(),
        config.db_path.stat().st_size,
    ) == before
    if wal_path.exists():
        assert wal_path.stat().st_size == 0

    shm_state = (
        (False, None) if not shm_path.exists() else (True, shm_path.stat().st_size)
    )
    assert not shm_state[0] or shm_state[1] is not None


def test_open_database_readonly_preserves_wal_while_writer_remains_open(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    writer = open_database(config)
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("main", "WAL read only"),
    )
    writer.commit()
    wal_path = Path(f"{config.db_path}-wal")
    assert wal_path.exists()
    before = (
        sha256(config.db_path.read_bytes()).hexdigest(),
        config.db_path.stat().st_size,
        sha256(wal_path.read_bytes()).hexdigest(),
        wal_path.stat().st_size,
    )

    try:
        readonly = database_module.open_database_readonly(config)
        try:
            assert readonly.execute("SELECT working_title FROM works").fetchone() == (
                "WAL read only",
            )
        finally:
            readonly.close()

        assert wal_path.exists()
        after = (
            sha256(config.db_path.read_bytes()).hexdigest(),
            config.db_path.stat().st_size,
            sha256(wal_path.read_bytes()).hexdigest(),
            wal_path.stat().st_size,
        )
        assert after == before
    finally:
        writer.close()
