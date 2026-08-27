from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _support import initialize_test_work, json_value

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import DeprecatedCanonForbiddenError, WorkScopeError
from novel_core.services.character_service import CharacterService
from novel_core.services.character_state_service import CharacterStateService
from novel_core.services.context_guards import ContextGuardService
from novel_core.services.context_service import ContextService
from novel_core.services.disclosure_service import DisclosureService
from novel_core.services.episode_reference_service import EpisodeReferenceService
from novel_core.services.information_service import InformationService
from novel_core.services.knowledge_service import KnowledgeService
from novel_core.services.narrative_service import NarrativeService


@pytest.fixture
def services(tmp_path: Path):
    db_path = tmp_path / "story.db"
    connection = open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )
    try:
        initialize_test_work(connection, "Phase 3")
        yield SimpleNamespace(
            connection=connection,
            character=CharacterService(connection),
            context=ContextService(connection),
            context_guards=ContextGuardService(connection),
            disclosure=DisclosureService(connection),
            information=InformationService(connection),
            knowledge=KnowledgeService(connection),
            narrative=NarrativeService(connection),
            references=EpisodeReferenceService(connection),
            state=CharacterStateService(connection),
        )
    finally:
        connection.close()


def test_future_character_knowledge_returns_only_safe_guard(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    future = services.narrative.create_episode(chapter.id, "未来話")
    character = services.character.create("AI")
    secret = services.information.create_information(
        "SECRET_FUTURE_BODY_9F28",
        authoring_guard="SECRET_FUTURE_BODY_9F28 を公開しない",
    )
    services.references.add(target.id, "character", character.id)
    services.references.add(target.id, "information", secret.id)
    services.disclosure.set_reader_disclosure(secret.id, future.id)
    services.knowledge.set_character_knowledge(
        character.id, secret.id, target.id, "knows"
    )

    context = services.context.build_episode_context(target.id)
    serialized = json.dumps(json_value(context), ensure_ascii=False)

    assert context.participants[0].known_information == ()
    assert any(
        guard.information_item_id == secret.id and guard.character_id == character.id
        for guard in context.protected_information_guards
    )
    assert "SECRET_FUTURE_BODY_9F28" not in serialized


def test_future_character_state_is_not_effective(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    future = services.narrative.create_episode(chapter.id, "未来話")
    character = services.character.create("主人公")
    services.references.add(target.id, "character", character.id)
    services.state.set_state(
        character.id, future.id, physical_state="SECRET_FUTURE_STATE"
    )

    context = services.context.build_episode_context(target.id)
    serialized = json.dumps(json_value(context), ensure_ascii=False)

    assert context.participants[0].effective_state is None
    assert "SECRET_FUTURE_STATE" not in serialized


def test_deprecated_information_is_excluded_from_context(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    item = services.information.create_information("SECRET_DEPRECATED_BODY")
    services.references.add(target.id, "information", item.id)
    canonical = services.information.update_information(
        item.id, item.version, canon_status="canon", reason="採用"
    )
    services.information.update_information(
        item.id, canonical.version, canon_status="deprecated", reason="撤回"
    )

    context = services.context.build_episode_context(target.id)
    serialized = json.dumps(json_value(context), ensure_ascii=False)

    assert context.reader_context.known_before_episode == ()
    assert context.reader_context.reveal_this_episode == ()
    assert "SECRET_DEPRECATED_BODY" not in serialized


def test_deprecated_target_fails_closed(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    canonical = services.narrative.update_episode(
        target.id, target.version, canon_status="canon", reason="採用"
    )
    services.narrative.update_episode(
        target.id, canonical.version, canon_status="deprecated", reason="撤回"
    )

    with pytest.raises(
        DeprecatedCanonForbiddenError, match="DEPRECATED_CANON_FORBIDDEN"
    ):
        services.context.build_episode_context(target.id)


def test_cross_work_target_fails_closed(services) -> None:
    services.connection.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        ("other", "Other Work"),
    )
    other_work_id = services.connection.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    services.connection.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, ?, ?)",
        (other_work_id, 1, "Other Chapter"),
    )
    other_chapter_id = services.connection.execute(
        "SELECT id FROM chapters WHERE work_id = ?", (other_work_id,)
    ).fetchone()[0]
    services.connection.execute(
        "INSERT INTO episodes "
        "(work_id, chapter_id, position, title) VALUES (?, ?, ?, ?)",
        (other_work_id, other_chapter_id, 1, "Other Episode"),
    )
    other_episode_id = services.connection.execute(
        "SELECT id FROM episodes WHERE work_id = ?", (other_work_id,)
    ).fetchone()[0]
    services.connection.commit()

    with pytest.raises(WorkScopeError, match="WORK_SCOPE_ERROR"):
        services.context.build_episode_context(other_episode_id)


def test_context_guard_service_reports_relevant_guards(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    secret = services.information.create_information("SECRET_GUARD_BODY")
    services.references.add(target.id, "information", secret.id)

    guards = services.context_guards.check_context_guards(target.id)

    assert len(guards) == 1
    assert guards[0].information_item_id == secret.id
    assert "SECRET_GUARD_BODY" not in json.dumps(json_value(guards))
