from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import (
    CanonReasonRequired,
    CharacterNotFoundError,
    VersionConflictError,
    WorkScopeError,
)
from novel_mcp.services.canon_service import CanonService
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

    with pytest.raises(CharacterNotFoundError, match="NOT_FOUND"):
        service.relationship.create(source.id, 9999, "trusts")
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*relation_type"):
        service.relationship.create(source.id, source.id, "   ")
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*self"):
        service.relationship.create(source.id, source.id, "trusts")
    assert service.connection.in_transaction is False


def test_relationship_canonical_update_requires_reason_and_creates_audit(service):
    source = service.character.create("A", None)
    target = service.character.create("B", None)
    relation = service.relationship.create(source.id, target.id, "trusts")
    CanonService(service.connection).set_canon_status(
        "relationship", relation.id, "canon", relation.version, "採用"
    )

    with pytest.raises(CanonReasonRequired, match="CANON_REASON_REQUIRED"):
        service.relationship.update(relation.id, 2, "respects")

    updated = service.relationship.update(relation.id, 2, "respects", reason="訂正理由")

    assert updated.relation_type == "respects"
    assert updated.version == 3
    assert service.connection.execute(
        "SELECT relationship_type, summary FROM relationships WHERE id = ?",
        (relation.id,),
    ).fetchone() == ("respects", "")
    assert service.connection.execute(
        """
        SELECT COUNT(*)
        FROM canon_decision_changes
        WHERE entity_type = 'relationship' AND entity_id = ?
        """,
        (relation.id,),
    ).fetchone() == (2,)


def test_relationship_search_caps_limit_and_distinguishes_work_scope(service):
    source = service.character.create("source", None)
    for index in range(101):
        target = service.character.create(f"target-{index}", None)
        service.relationship.create(source.id, target.id, "knows")

    assert len(service.relationship.search(None, limit=1000)) == 100

    service.connection.execute(
        "INSERT INTO works (slug, title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = service.connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    service.connection.execute(
        """
        INSERT INTO characters
            (work_id, character_key, display_name, summary, canon_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (other_work_id, "other-character", "他作品", "", "draft"),
    )
    other_character_id = service.connection.execute(
        "SELECT id FROM characters WHERE character_key = ?", ("other-character",)
    ).fetchone()[0]
    service.connection.commit()

    with pytest.raises(WorkScopeError, match="WORK_SCOPE_ERROR"):
        service.relationship.create(source.id, other_character_id, "knows")


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
