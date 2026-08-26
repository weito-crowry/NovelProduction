from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import (
    CanonReasonRequired,
    CharacterNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkScopeError,
)
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.narrative_service import NarrativeService
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
                "narrative": NarrativeService(connection),
                "relationship": RelationshipService(connection),
            },
        )()
    finally:
        connection.close()


def test_relationship_direction_and_description_are_preserved(service) -> None:
    protagonist = service.character.create("主人公")
    mentor = service.character.create("師匠")
    relation = service.relationship.create(
        protagonist.id, mentor.id, "trusts", "信頼関係"
    )
    assert (relation.source_character_id, relation.target_character_id) == (
        protagonist.id,
        mentor.id,
    )
    assert relation.description == "信頼関係"
    assert service.relationship.search(mentor.id, 10) == (relation,)
    assert service.relationship.search(protagonist.id, 10) == (relation,)


def test_relationship_update_uses_cas(service) -> None:
    source = service.character.create("A")
    target = service.character.create("B")
    relation = service.relationship.create(source.id, target.id, "trusts")
    updated = service.relationship.update(
        relation.id, relation.version, "respects", description="敬意"
    )
    assert (updated.relationship_type, updated.description, updated.version) == (
        "respects",
        "敬意",
        2,
    )
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.relationship.update(relation.id, relation.version, "ignored")


def test_relationship_validates_endpoints_before_transaction(service) -> None:
    source = service.character.create("A")
    with pytest.raises(CharacterNotFoundError, match="NOT_FOUND"):
        service.relationship.create(source.id, 9999, "trusts")
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*relation_type"):
        service.relationship.create(source.id, source.id, "   ")
    with pytest.raises(ValueError, match="VALIDATION_ERROR.*self"):
        service.relationship.create(source.id, source.id, "trusts")
    assert service.connection.in_transaction is False


def test_relationship_canonical_update_requires_reason_and_audits(service) -> None:
    source = service.character.create("A")
    target = service.character.create("B")
    relation = service.relationship.create(source.id, target.id, "trusts")
    CanonService(service.connection).set_canon_status(
        "relationship", relation.id, "canon", relation.version, "採用"
    )
    with pytest.raises(CanonReasonRequired, match="CANON_REASON_REQUIRED"):
        service.relationship.update(relation.id, 2, "respects")
    updated = service.relationship.update(relation.id, 2, "respects", reason="訂正理由")
    assert updated.relationship_type == "respects"
    assert service.connection.execute(
        "SELECT relationship_type, description FROM relationships WHERE id = ?",
        (relation.id,),
    ).fetchone() == ("respects", "")
    assert service.connection.execute(
        "SELECT COUNT(*) FROM canon_decisions"
    ).fetchone() == (2,)


def test_relationship_search_caps_limit_and_distinguishes_work_scope(service) -> None:
    source = service.character.create("source")
    for index in range(101):
        target = service.character.create(f"target-{index}")
        service.relationship.create(source.id, target.id, "knows")
    assert len(service.relationship.search(None, 1000)) == 100
    service.connection.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = service.connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    service.connection.execute(
        "INSERT INTO characters "
        "(work_id, character_key, display_name, description, canon_status) "
        "VALUES (?, ?, ?, ?, ?)",
        (other_work_id, "other-character", "他作品", "", "draft"),
    )
    other_character_id = service.connection.execute(
        "SELECT id FROM characters WHERE character_key = ?", ("other-character",)
    ).fetchone()[0]
    service.connection.commit()
    with pytest.raises(WorkScopeError, match="WORK_SCOPE_ERROR"):
        service.relationship.create(source.id, other_character_id, "knows")


def test_relationship_search_is_deterministic_and_isolated(service) -> None:
    first = service.character.create("一")
    second = service.character.create("二")
    third = service.character.create("三")
    first_relation = service.relationship.create(first.id, second.id, "knows")
    second_relation = service.relationship.create(second.id, third.id, "helps")
    assert service.relationship.search(None, 10) == (first_relation, second_relation)
    assert service.relationship.search(second.id, 1) == (first_relation,)
    assert service.relationship.search(None, 0) == ()


def test_temporal_relationships_use_inclusive_start_and_exclusive_end(service) -> None:
    source = service.character.create("A")
    target = service.character.create("B")
    chapter = service.narrative.create_chapter("章")
    episodes = [
        service.narrative.create_episode(chapter.id, f"話{i}") for i in range(1, 4)
    ]

    relation = service.relationship.create(
        source.id,
        target.id,
        "ally",
        valid_from_episode_id=episodes[0].id,
        valid_to_episode_id=episodes[2].id,
    )

    assert (relation.valid_from_episode_id, relation.valid_to_episode_id) == (
        episodes[0].id,
        episodes[2].id,
    )
    assert service.relationship.effective_at(episodes[0].id) == (relation,)
    assert service.relationship.effective_at(episodes[1].id) == (relation,)
    assert service.relationship.effective_at(episodes[2].id) == ()


def test_temporal_relationships_allow_adjacent_ranges_and_reject_overlap(
    service,
) -> None:
    source = service.character.create("A")
    target = service.character.create("B")
    chapter = service.narrative.create_chapter("章")
    episodes = [
        service.narrative.create_episode(chapter.id, f"話{i}") for i in range(1, 4)
    ]
    service.relationship.create(
        source.id,
        target.id,
        "ally",
        valid_from_episode_id=episodes[0].id,
        valid_to_episode_id=episodes[1].id,
    )
    adjacent = service.relationship.create(
        source.id,
        target.id,
        "ally",
        valid_from_episode_id=episodes[1].id,
        valid_to_episode_id=episodes[2].id,
    )
    assert adjacent.valid_from_episode_id == episodes[1].id
    with pytest.raises(ValidationError, match="RELATION_INTEGRITY_ERROR"):
        service.relationship.create(
            source.id,
            target.id,
            "ally",
            valid_from_episode_id=episodes[0].id,
            valid_to_episode_id=episodes[2].id,
        )
