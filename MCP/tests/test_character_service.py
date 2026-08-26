from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import CanonReasonRequired, VersionConflictError
from novel_mcp.services.canon_service import CanonService
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


def test_character_create_maps_normalized_fields(service: CharacterService) -> None:
    character = service.create(
        character_key="protagonist",
        display_name="  主人公  ",
        entity_type="human",
        description="赤い都市の調査員",
        birth_date="2080-01-02",
        occupation="調査員",
        profile_json='{"voice":"calm"}',
    )
    assert character.name == "主人公"
    assert character.display_name == "主人公"
    assert character.description == "赤い都市の調査員"
    assert character.entity_type == "human"
    assert character.birth_date == "2080-01-02"
    assert character.profile_json == '{"voice":"calm"}'
    assert service._connection.execute(
        "SELECT character_key, display_name, entity_type, description, "
        "canon_status FROM characters WHERE id = ?",
        (character.id,),
    ).fetchone() == ("protagonist", "主人公", "human", "赤い都市の調査員", "draft")


def test_character_update_requires_expected_version_and_preserves_omitted_fields(
    service: CharacterService,
) -> None:
    character = service.create("主人公", "最初の設定")
    updated = service.update(character.id, character.version, name="主人公改")
    assert updated.name == "主人公改"
    assert updated.profile == "最初の設定"
    assert updated.version == 2
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.update(character.id, character.version, profile="競合")


def test_character_search_is_deterministic_and_scoped(
    service: CharacterService,
) -> None:
    first = service.create("火星の主人公", "赤い都市")
    second = service.create("火星の師匠", "主人公を導く")
    connection = service._connection
    connection.execute(
        "INSERT INTO works (slug, title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO characters "
        "(work_id, character_key, display_name, description, canon_status) "
        "VALUES (?, ?, ?, ?, ?)",
        (other_work_id, "other-key", "火星の別人", "主人公", "draft"),
    )
    connection.commit()
    assert service.search("主人公", 10) == (first, second)
    assert service.search("不存在", 10) == ()
    assert service.search("主人公", 0) == ()


def test_character_get_missing_and_invalid_input_are_structured(
    service: CharacterService,
) -> None:
    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        service.get(9999)
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*display_name"):
        service.create("   ")


def test_character_canonical_update_requires_reason(service: CharacterService) -> None:
    character = service.create("主人公", "旧設定")
    CanonService(service._connection).set_canon_status(
        "character", character.id, "canon", character.version, "採用"
    )
    with pytest.raises(CanonReasonRequired, match="CANON_REASON_REQUIRED"):
        service.update(character.id, 2, name="主人公改")
    updated = service.update(
        character.id,
        2,
        display_name="主人公改",
        description="新設定",
        reason="訂正理由",
    )
    assert (updated.name, updated.profile, updated.version) == ("主人公改", "新設定", 3)
    assert service._connection.execute(
        "SELECT display_name, description FROM characters WHERE id = ?", (character.id,)
    ).fetchone() == ("主人公改", "新設定")


def test_character_search_caps_limit_at_service_bound(
    service: CharacterService,
) -> None:
    for index in range(101):
        service.create(f"火星の人物 {index}")
    assert len(service.search("火星の人物", 1000)) == 100
