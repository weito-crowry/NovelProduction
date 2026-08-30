from __future__ import annotations

import sqlite3
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from novel_core.config import DatabaseConfig
from novel_core.database import assert_database_integrity, open_database
from novel_core.errors import DatabaseIntegrityError, MigrationError

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATION_NAMES = (
    "001_initial.sql",
    "002_search.sql",
    "003_narrative.sql",
    "004_drafts.sql",
    "005_structured_drafts.sql",
)


class _FakeCursor:
    def __init__(self, rows: tuple[tuple[str], ...]) -> None:
        self._rows = rows

    def fetchall(self) -> tuple[tuple[str], ...]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: tuple[tuple[str], ...]) -> None:
        self._rows = rows

    def execute(self, statement: str) -> _FakeCursor:
        assert statement == "PRAGMA integrity_check;"
        return _FakeCursor(self._rows)


class _SetupFailureConnection:
    def __init__(self) -> None:
        self.closed = False

    def execute(self, statement: str) -> None:
        if statement == "PRAGMA journal_mode = WAL;":
            raise sqlite3.OperationalError("setup failed")

    def close(self) -> None:
        self.closed = True


def _simple_migration(eol: bytes) -> bytes:
    return (
        b"CREATE TABLE schema_migrations "
        b"(version TEXT PRIMARY KEY, checksum TEXT NOT NULL);" + eol
    )


def _migration_bytes_with_eol(raw: bytes, eol: bytes) -> bytes:
    canonical_lf = raw.replace(b"\r\n", b"\n")
    if eol == b"\n":
        return canonical_lf
    return canonical_lf.replace(b"\n", b"\r\n")


def _copy_migrations_with_eol(destination: Path, eols: dict[str, bytes]) -> None:
    destination.mkdir()
    for name in MIGRATION_NAMES:
        raw = (MIGRATION_DIR / name).read_bytes()
        (destination / name).write_bytes(_migration_bytes_with_eol(raw, eols[name]))


def _seed_legacy_database(
    db_path: Path, migration_dir: Path, migration_names: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    connection = sqlite3.connect(db_path)
    try:
        for name in migration_names:
            migration_path = migration_dir / name
            connection.executescript(migration_path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version, checksum) VALUES (?, ?)",
                (name, sha256(migration_path.read_bytes()).hexdigest()),
            )
        connection.commit()
        return tuple(
            connection.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
    finally:
        connection.close()


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
        assert tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ) == (
            "001_initial.sql",
            "002_search.sql",
            "003_narrative.sql",
            "004_drafts.sql",
            "005_structured_drafts.sql",
        )
    finally:
        connection.close()


def test_open_database_closes_connection_when_setup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _SetupFailureConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda _db_path: connection)

    with pytest.raises(sqlite3.OperationalError, match="setup failed"):
        open_database(
            DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
        )

    assert connection.closed is True


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
        assert second_connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            ("002_search.sql",),
        ).fetchone() == (1,)
        assert second_connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            ("003_narrative.sql",),
        ).fetchone() == (1,)
        assert second_connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            ("004_drafts.sql",),
        ).fetchone() == (1,)
        assert second_connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            ("005_structured_drafts.sql",),
        ).fetchone() == (1,)
    finally:
        second_connection.close()


def test_migration_checksums_match_canonical_lf_bytes(
    tmp_path: Path,
) -> None:
    migration_dir = MIGRATION_DIR
    config = DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=migration_dir)
    connection = open_database(config)
    try:
        rows = connection.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        expected = tuple(
            (
                path.name,
                sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            )
            for path in sorted(migration_dir.glob("*.sql"))
        )
        assert tuple(rows) == expected
    finally:
        connection.close()


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

    with pytest.raises(MigrationError, match="001_initial.sql"):
        open_database(DatabaseConfig(db_path=db_path, migration_dir=migration_dir))


def test_open_database_accepts_crlf_checkout_after_lf_application(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "story.db"
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    migration_file = migration_dir / "001_initial.sql"
    migration_file.write_bytes(_simple_migration(b"\n"))

    connection = open_database(
        DatabaseConfig(db_path=db_path, migration_dir=migration_dir)
    )
    stored_rows = tuple(
        connection.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    )
    connection.close()

    migration_file.write_bytes(_simple_migration(b"\r\n"))
    reopened = open_database(
        DatabaseConfig(db_path=db_path, migration_dir=migration_dir)
    )
    try:
        assert (
            tuple(
                reopened.execute(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
            )
            == stored_rows
        )
    finally:
        reopened.close()


def test_open_database_accepts_lf_checkout_after_crlf_legacy_checksum(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "story.db"
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    migration_file = migration_dir / "001_initial.sql"
    migration_file.write_bytes(_simple_migration(b"\r\n"))

    stored_rows = _seed_legacy_database(db_path, migration_dir, ("001_initial.sql",))
    migration_file.write_bytes(_simple_migration(b"\n"))

    reopened = open_database(
        DatabaseConfig(db_path=db_path, migration_dir=migration_dir)
    )
    try:
        assert (
            tuple(
                reopened.execute(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
            )
            == stored_rows
        )
    finally:
        reopened.close()


def test_new_migration_checksum_is_eol_independent(tmp_path: Path) -> None:
    checksums = []
    for eol in (b"\n", b"\r\n"):
        migration_dir = tmp_path / (
            "migrations-lf" if eol == b"\n" else "migrations-crlf"
        )
        migration_dir.mkdir()
        (migration_dir / "001_initial.sql").write_bytes(_simple_migration(eol))
        connection = open_database(
            DatabaseConfig(
                db_path=tmp_path / ("lf.db" if eol == b"\n" else "crlf.db"),
                migration_dir=migration_dir,
            )
        )
        try:
            checksums.append(
                connection.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = ?",
                    ("001_initial.sql",),
                ).fetchone()[0]
            )
        finally:
            connection.close()

    assert checksums == [
        sha256(_simple_migration(b"\n")).hexdigest(),
        sha256(_simple_migration(b"\n")).hexdigest(),
    ]


def test_assert_database_integrity_accepts_single_ok_row(tmp_path: Path) -> None:
    connection = open_database(
        DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    )
    try:
        assert_database_integrity(connection)
    finally:
        connection.close()


@pytest.mark.parametrize(
    "rows",
    [
        (),
        (("not ok",),),
        (("ok",), ("still ok",)),
    ],
    ids=["missing", "bad-result", "multiple-rows"],
)
def test_assert_database_integrity_rejects_non_ok_results(
    rows: tuple[tuple[str], ...],
) -> None:
    connection = cast(sqlite3.Connection, _FakeConnection(rows))

    with pytest.raises(DatabaseIntegrityError):
        assert_database_integrity(connection)


@pytest.mark.parametrize("current_eol", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_open_database_accepts_mixed_legacy_checksums_without_rewriting_ledger(
    tmp_path: Path, current_eol: bytes
) -> None:
    db_path = tmp_path / "story.db"
    legacy_dir = tmp_path / "legacy-migrations"
    _copy_migrations_with_eol(
        legacy_dir,
        {
            "001_initial.sql": b"\r\n",
            "002_search.sql": b"\r\n",
            "003_narrative.sql": b"\r\n",
            "004_drafts.sql": b"\n",
            "005_structured_drafts.sql": b"\n",
        },
    )

    stored_rows = _seed_legacy_database(db_path, legacy_dir, MIGRATION_NAMES)
    current_dir = tmp_path / "current-migrations"
    _copy_migrations_with_eol(
        current_dir, {name: current_eol for name in MIGRATION_NAMES}
    )

    reopened = open_database(DatabaseConfig(db_path=db_path, migration_dir=current_dir))
    try:
        assert (
            tuple(
                reopened.execute(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
            )
            == stored_rows
        )
    finally:
        reopened.close()


def test_phase1_core_schema_has_normalized_fields_and_sqlite_invariants(
    tmp_path: Path,
) -> None:
    config = DatabaseConfig(
        db_path=tmp_path / "story.db",
        migration_dir=Path(__file__).resolve().parents[1] / "migrations",
    )
    connection = open_database(config)

    try:
        expected_columns = {
            "works": {
                "id",
                "slug",
                "working_title",
                "genre",
                "premise",
                "themes_json",
                "description",
                "production_status",
                "version",
                "created_at",
                "updated_at",
            },
            "world_facts": {
                "id",
                "work_id",
                "topic_key",
                "category",
                "title",
                "statement",
                "details_json",
                "valid_from",
                "valid_to",
                "canon_status",
                "importance",
                "version",
                "created_at",
                "updated_at",
            },
            "characters": {
                "id",
                "work_id",
                "character_key",
                "display_name",
                "entity_type",
                "description",
                "birth_date",
                "death_date",
                "physical_description",
                "occupation",
                "core_beliefs",
                "goals",
                "fears",
                "personality",
                "speech_style",
                "ai_attitude",
                "genetic_modification_attitude",
                "private_notes",
                "profile_json",
                "canon_status",
                "version",
                "created_at",
                "updated_at",
            },
            "timeline_events": {
                "id",
                "work_id",
                "event_key",
                "time_start",
                "time_end",
                "date_precision",
                "date_display",
                "title",
                "description",
                "category",
                "location_world_fact_id",
                "cause_summary",
                "consequence_summary",
                "canon_status",
                "importance",
                "version",
                "created_at",
                "updated_at",
            },
            "timeline_event_participants": {
                "id",
                "event_id",
                "character_id",
                "role",
                "created_at",
            },
            "relationships": {
                "id",
                "work_id",
                "source_character_id",
                "target_character_id",
                "relationship_type",
                "description",
                "canon_status",
                "valid_from_episode_id",
                "valid_to_episode_id",
                "version",
                "created_at",
                "updated_at",
            },
        }
        for table, columns in expected_columns.items():
            actual = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert actual == columns, table

        connection.execute(
            "INSERT INTO works (slug, working_title) VALUES (?, ?)", ("main", "Main")
        )
        work_id = connection.execute("SELECT id FROM works").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO world_facts
                   (work_id, topic_key, category, title, statement, canon_status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (work_id, "fact", "setting", "Title", "Statement", "invalid"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO world_facts
                   (work_id, topic_key, category, title, statement, version)
                   VALUES (?, ?, ?, ?, ?, 0)""",
                (work_id, "fact", "setting", "Title", "Statement"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO works (slug, working_title, themes_json) VALUES (?, ?, ?)",
                ("invalid-json", "Invalid", "not-json"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO works (slug, working_title, production_status) "
                "VALUES (?, ?, ?)",
                ("invalid-status", "Invalid", "unknown"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO characters
                   (work_id, character_key, display_name, entity_type)
                   VALUES (?, ?, ?, ?)""",
                (work_id, "char", "Character", "robot"),
            )
        connection.execute(
            """INSERT INTO world_facts
               (work_id, topic_key, category, title, statement)
               VALUES (?, ?, ?, ?, ?)""",
            (work_id, "place", "setting", "Place", "Place"),
        )
        fact_id = connection.execute("SELECT id FROM world_facts").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO timeline_events
                   (work_id, event_key, date_precision, date_display, title,
                    location_world_fact_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (work_id, "event", "day", "2104-01-01", "Event", fact_id + 999),
            )
        connection.execute(
            """INSERT INTO characters
               (work_id, character_key, display_name, entity_type)
               VALUES (?, ?, ?, ?)""",
            (work_id, "char", "Character", "human"),
        )
        character_id = connection.execute("SELECT id FROM characters").fetchone()[0]
        connection.execute(
            """INSERT INTO timeline_events
               (work_id, event_key, time_start, time_end, date_precision,
                date_display, title)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                work_id,
                "event",
                "2104-01-01",
                "2104-01-01",
                "day",
                "2104-01-01",
                "Event",
            ),
        )
        event_id = connection.execute("SELECT id FROM timeline_events").fetchone()[0]
        connection.execute(
            "INSERT INTO timeline_event_participants "
            "(event_id, character_id, role) VALUES (?, ?, ?)",
            (event_id, character_id, "observer"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO timeline_event_participants "
                "(event_id, character_id, role) VALUES (?, ?, ?)",
                (event_id, character_id + 999, "invalid"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO relationships
                    (work_id, source_character_id, target_character_id,
                     relationship_type)
                VALUES (?, ?, ?, ?)
                """,
                (work_id, character_id, character_id + 999, "knows"),
            )
        connection.commit()
    finally:
        connection.close()
