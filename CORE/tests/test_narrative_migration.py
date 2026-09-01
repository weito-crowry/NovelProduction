from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from novel_core.config import DatabaseConfig
from novel_core.database import open_database

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture
def database(tmp_path: Path) -> sqlite3.Connection:
    connection = open_database(
        DatabaseConfig(
            db_path=tmp_path / "story.db",
            migration_dir=MIGRATION_DIR,
        )
    )
    connection.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("main", "Main"),
    )
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def test_phase2_migration_creates_required_tables_and_columns(
    database: sqlite3.Connection,
) -> None:
    table_columns = {
        table: {row[1] for row in database.execute(f"PRAGMA table_info({table})")}
        for table in (
            "chapters",
            "episodes",
            "scenes",
            "character_states",
            "information_items",
            "reader_disclosures",
            "character_knowledge_events",
            "episode_characters",
            "episode_world_facts",
            "episode_timeline_events",
            "episode_information",
        )
    }

    assert table_columns == {
        "chapters": {
            "id",
            "work_id",
            "position",
            "title",
            "summary",
            "purpose",
            "canon_status",
            "production_status",
            "version",
            "created_at",
            "updated_at",
        },
        "episodes": {
            "id",
            "work_id",
            "chapter_id",
            "position",
            "title",
            "summary",
            "purpose",
            "foreshadowing_notes_json",
            "canon_status",
            "production_status",
            "version",
            "created_at",
            "updated_at",
        },
        "scenes": {
            "id",
            "work_id",
            "episode_id",
            "position",
            "title",
            "summary",
            "purpose",
            "canon_status",
            "production_status",
            "version",
            "created_at",
            "updated_at",
        },
        "character_states": {
            "id",
            "work_id",
            "character_id",
            "episode_id",
            "physical_state",
            "emotional_state",
            "beliefs_json",
            "location_world_fact_id",
            "state_json",
            "version",
            "created_at",
            "updated_at",
        },
        "information_items": {
            "id",
            "work_id",
            "statement",
            "truth_status",
            "authoring_guard",
            "notes_json",
            "canon_status",
            "importance",
            "version",
            "created_at",
            "updated_at",
        },
        "reader_disclosures": {
            "id",
            "work_id",
            "information_item_id",
            "episode_id",
            "version",
            "created_at",
            "updated_at",
        },
        "character_knowledge_events": {
            "id",
            "work_id",
            "character_id",
            "information_item_id",
            "episode_id",
            "knowledge_state",
            "note",
            "version",
            "created_at",
            "updated_at",
        },
        "episode_characters": {
            "id",
            "work_id",
            "episode_id",
            "character_id",
            "role",
            "created_at",
        },
        "episode_world_facts": {
            "id",
            "work_id",
            "episode_id",
            "world_fact_id",
            "created_at",
        },
        "episode_timeline_events": {
            "id",
            "work_id",
            "episode_id",
            "timeline_event_id",
            "created_at",
        },
        "episode_information": {
            "id",
            "work_id",
            "episode_id",
            "information_item_id",
            "created_at",
        },
    }

    relationship_columns = {
        row[1] for row in database.execute("PRAGMA table_info(relationships)")
    }
    assert {"valid_from_episode_id", "valid_to_episode_id"} <= relationship_columns
    assert tuple(
        row[0]
        for row in database.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ) == (
        "001_initial.sql",
        "002_search.sql",
        "003_narrative.sql",
        "004_drafts.sql",
        "005_structured_drafts.sql",
        "006_style_analysis_foundation.sql",
        "007_style_analysis_semantics.sql",
    )

    tables = {
        row[0]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "drafts" in tables
    assert {
        "id",
        "work_id",
        "episode_id",
        "revision",
        "parent_draft_id",
        "document_json",
        "source_agent",
        "change_summary",
        "created_at",
    } == {row[1] for row in database.execute("PRAGMA table_info(drafts)")}


def test_phase2_constraints_cover_status_positions_and_json(
    database: sqlite3.Connection,
) -> None:
    work_id = database.execute("SELECT id FROM works").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO chapters (work_id, position, title) VALUES (?, 0, ?)",
            (work_id, "invalid"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO chapters (work_id, position, title, canon_status) "
            "VALUES (?, 1, ?, ?)",
            (work_id, "invalid", "future"),
        )
    database.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, ?)",
        (work_id, "第一章"),
    )
    chapter_id = database.execute("SELECT id FROM chapters").fetchone()[0]
    database.execute(
        "INSERT INTO episodes (work_id, chapter_id, position, title) "
        "VALUES (?, ?, 1, ?)",
        (work_id, chapter_id, "第一話"),
    )
    assert database.execute(
        "SELECT foreshadowing_notes_json FROM episodes"
    ).fetchone() == ("[]",)
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO information_items "
            "(work_id, statement, notes_json, importance) VALUES (?, ?, ?, -1)",
            (work_id, "statement", "{}"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO information_items "
            "(work_id, statement, notes_json) VALUES (?, ?, ?)",
            (work_id, "statement", "not-json"),
        )
    database.rollback()


def test_relationship_rebuild_preserves_existing_rows_and_removes_old_unique(
    tmp_path: Path,
) -> None:
    phase1_migrations = tmp_path / "phase1_migrations"
    phase1_migrations.mkdir()
    for migration_name in ("001_initial.sql", "002_search.sql"):
        shutil.copyfile(
            MIGRATION_DIR / migration_name, phase1_migrations / migration_name
        )

    db_path = tmp_path / "story.db"
    old = open_database(
        DatabaseConfig(db_path=db_path, migration_dir=phase1_migrations)
    )
    old.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("main", "Main"),
    )
    work_id = old.execute("SELECT id FROM works").fetchone()[0]
    old.execute(
        "INSERT INTO characters "
        "(work_id, character_key, display_name, entity_type) VALUES (?, ?, ?, ?)",
        (work_id, "a", "A", "human"),
    )
    source_id = old.execute("SELECT id FROM characters").fetchone()[0]
    old.execute(
        "INSERT INTO characters "
        "(work_id, character_key, display_name, entity_type) VALUES (?, ?, ?, ?)",
        (work_id, "b", "B", "human"),
    )
    target_id = old.execute(
        "SELECT id FROM characters WHERE character_key = 'b'"
    ).fetchone()[0]
    old.execute(
        "INSERT INTO relationships "
        "(work_id, source_character_id, target_character_id, "
        "relationship_type, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (work_id, source_id, target_id, "ally", "legacy"),
    )
    old.commit()
    old.close()

    upgraded = open_database(
        DatabaseConfig(db_path=db_path, migration_dir=MIGRATION_DIR)
    )
    try:
        row = upgraded.execute(
            "SELECT id, work_id, description, canon_status, version, created_at, "
            "updated_at, valid_from_episode_id, valid_to_episode_id FROM relationships"
        ).fetchone()
        assert row is not None
        assert row[1:5] == (work_id, "legacy", "draft", 1)
        assert row[7:] == (None, None)
        unique_indexes = [
            database_row
            for database_row in upgraded.execute("PRAGMA index_list(relationships)")
            if database_row[2]
        ]
        assert not any(
            tuple(
                column[2]
                for column in upgraded.execute(f"PRAGMA index_info('{index[1]}')")
            )
            == ("source_character_id", "target_character_id", "relationship_type")
            for index in unique_indexes
        )
    finally:
        upgraded.close()
