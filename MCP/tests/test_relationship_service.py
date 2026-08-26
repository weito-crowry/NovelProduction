from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import VersionConflictError
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.relationship_service import RelationshipService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


def test_character_and_relationship_services_contain_no_sql_tokens() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "novel_mcp" / "services"
    forbidden_tokens = ("SELECT", "INSERT", "UPDATE", "DELETE", "BEGIN")

    for module_name in ("character_service.py", "relationship_service.py"):
        source = (source_root / module_name).read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden_tokens), module_name


@pytest.fixture
def service(tmp_path: Path):
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)
    try:
        yield type(
            "Services",
            (),
            {
                "connection": connection,
                "character": CharacterService(connection),
                "relationship": RelationshipService(connection),
            },
        )()
    finally:
        connection.close()


def test_relationship_direction_is_preserved_without_reciprocal_inference(service):
    protagonist = service.character.create("主人公", None)
    mentor = service.character.create("師匠", None)
    relation = service.relationship.create(protagonist.id, mentor.id, "trusts")

    assert relation.source_character_id == protagonist.id
    assert relation.target_character_id == mentor.id
    assert service.relationship.search(mentor.id, limit=10) == (relation,)
    assert service.relationship.search(protagonist.id, limit=10) == (relation,)
    assert (
        service.relationship.create(
            mentor.id, protagonist.id, "trusts"
        ).source_character_id
        == mentor.id
    )


def test_relationship_update_uses_cas_and_hides_adapter_fields(service):
    source = service.character.create("A", None)
    target = service.character.create("B", None)
    relation = service.relationship.create(source.id, target.id, "trusts")

    updated = service.relationship.update(
        relation.id, relation.version, relation_type="respects"
    )
    assert updated.relation_type == "respects"
    assert updated.version == 2
    assert set(updated.__dataclass_fields__) == {
        "id",
        "source_character_id",
        "target_character_id",
        "relation_type",
        "created_at",
        "updated_at",
        "version",
    }
    row = service.connection.execute(
        "SELECT summary, canon_status FROM relationships WHERE id = ?",
        (relation.id,),
    ).fetchone()
    assert row == ("", "draft")

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.relationship.update(relation.id, relation.version, "ignored")


def test_relationship_validates_endpoints_before_transaction(service):
    source = service.character.create("A", None)

    with pytest.raises(RuntimeError, match="NOT_FOUND"):
        service.relationship.create(source.id, 9999, "trusts")
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*relation_type"):
        service.relationship.create(source.id, source.id, "   ")
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*self"):
        service.relationship.create(source.id, source.id, "trusts")
    assert service.connection.in_transaction is False


def test_relationship_search_is_deterministic_and_isolated(service):
    first = service.character.create("一", None)
    second = service.character.create("二", None)
    third = service.character.create("三", None)
    first_relation = service.relationship.create(first.id, second.id, "knows")
    second_relation = service.relationship.create(second.id, third.id, "helps")

    assert service.relationship.search(None, limit=10) == (
        first_relation,
        second_relation,
    )
    assert service.relationship.search(second.id, limit=1) == (first_relation,)
    assert service.relationship.search(None, limit=0) == ()
