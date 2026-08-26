from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import VersionConflictError
from novel_mcp.services.character_service import CharacterService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def service(tmp_path: Path):
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)
    try:
        yield CharacterService(connection)
    finally:
        connection.close()


def test_character_create_maps_public_fields_and_hides_schema_defaults(service):
    character = service.create("  主人公  ", None)

    assert character.name == "主人公"
    assert character.profile == ""
    assert character.version == 1
    assert set(character.__dataclass_fields__) == {
        "id",
        "name",
        "profile",
        "created_at",
        "updated_at",
        "version",
    }
    row = service._connection.execute(
        "SELECT character_key, display_name, summary, canon_status "
        "FROM characters WHERE id = ?",
        (character.id,),
    ).fetchone()
    assert row[0]
    assert row[1:] == ("主人公", "", "draft")


def test_character_update_requires_expected_version_and_preserves_omitted_fields(
    service,
):
    character = service.create("主人公", "最初の設定")

    updated = service.update(character.id, character.version, name="  主人公改  ")
    assert updated.name == "主人公改"
    assert updated.profile == "最初の設定"
    assert updated.version == 2

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.update(character.id, character.version, profile="競合")


def test_character_search_is_deterministic_and_scoped(service):
    first = service.create("火星の主人公", "赤い都市")
    second = service.create("火星の師匠", "主人公を導く")
    other_connection = service._connection
    other_connection.execute(
        "INSERT INTO works (slug, title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = other_connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    other_connection.execute(
        "INSERT INTO characters "
        "(work_id, character_key, display_name, summary, canon_status) "
        "VALUES (?, ?, ?, ?, ?)",
        (other_work_id, "other-key", "火星の別人", "主人公", "draft"),
    )
    other_connection.commit()

    assert service.search("主人公", limit=10) == (first, second)
    assert service.search("不存在", limit=10) == ()
    assert service.search("主人公", limit=0) == ()


def test_character_get_missing_and_invalid_input_are_structured(service):
    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        service.get(9999)
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*name"):
        service.create("   ", None)
