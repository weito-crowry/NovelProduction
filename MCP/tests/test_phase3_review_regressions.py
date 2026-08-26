from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.models.context import ReaderContext
from novel_mcp.models.outline import SafeInformationItem
from novel_mcp.phase3_acceptance import (
    _future_disclosure_ok,
    _has_deprecated,
    run_phase3_acceptance,
)
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.character_state_service import CharacterStateService
from novel_mcp.services.context_service import ContextService
from novel_mcp.services.disclosure_service import DisclosureService
from novel_mcp.services.episode_reference_service import EpisodeReferenceService
from novel_mcp.services.information_service import InformationService
from novel_mcp.services.narrative_service import NarrativeService
from novel_mcp.tool_errors import json_value


@pytest.fixture
def services(tmp_path: Path):
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "Phase 3 review")
    connection = open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )
    try:
        yield SimpleNamespace(
            connection=connection,
            character=CharacterService(connection),
            state=CharacterStateService(connection),
            context=ContextService(connection),
            disclosure=DisclosureService(connection),
            information=InformationService(connection),
            narrative=NarrativeService(connection),
            references=EpisodeReferenceService(connection),
        )
    finally:
        connection.close()


def test_current_reveal_is_canonical_without_episode_reference_or_knowledge(
    services,
) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    item = services.information.create_information("この話で開示する")
    services.disclosure.set_reader_disclosure(item.id, target.id)

    context = services.context.build_episode_context(target.id)

    assert [value.id for value in context.reader_context.reveal_this_episode] == [
        item.id
    ]
    assert context.reader_context.reveal_this_episode[0].statement == "この話で開示する"


def test_current_reveal_is_deduplicated_when_also_referenced(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    item = services.information.create_information("重複しない開示")
    services.disclosure.set_reader_disclosure(item.id, target.id)
    services.references.add(target.id, "information", item.id)

    context = services.context.build_episode_context(target.id)

    assert [value.id for value in context.reader_context.reveal_this_episode] == [
        item.id
    ]


def test_current_reveals_are_critical_and_not_capped_at_fifty(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    item_ids: list[int] = []
    for index in range(55):
        item = services.information.create_information(f"current reveal {index}")
        item_ids.append(item.id)
        services.disclosure.set_reader_disclosure(item.id, target.id)

    context = services.context.build_episode_context(target.id)

    assert [
        value.id for value in context.reader_context.reveal_this_episode
    ] == item_ids
    assert len(context.reader_context.reveal_this_episode) == 55


def test_deprecated_current_reveal_is_excluded(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    item = services.information.create_information("撤回済み開示")
    services.disclosure.set_reader_disclosure(item.id, target.id)
    canonical = services.information.update_information(
        item.id, item.version, canon_status="canon", reason="採用"
    )
    services.information.update_information(
        item.id, canonical.version, canon_status="deprecated", reason="撤回"
    )

    context = services.context.build_episode_context(target.id)

    assert context.reader_context.reveal_this_episode == ()


def test_effective_state_exposes_structured_beliefs_but_not_state_json(
    services,
) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    character = services.character.create("主人公")
    services.references.add(target.id, "character", character.id)
    services.state.set_state(
        character.id,
        target.id,
        beliefs_json={"AI": "信頼している", "risk": 0.25},
        state_json={"secret": "STATE_JSON_MUST_NOT_LEAK"},
    )

    context = services.context.build_episode_context(target.id)
    payload = json.dumps(json_value(context), ensure_ascii=False)

    assert context.participants[0].effective_state is not None
    assert context.participants[0].effective_state.beliefs == {
        "AI": "信頼している",
        "risk": 0.25,
    }
    assert "STATE_JSON_MUST_NOT_LEAK" not in payload


def test_effective_beliefs_follow_narrative_order_after_reorder(services) -> None:
    chapter = services.narrative.create_chapter("章")
    state_episode = services.narrative.create_episode(chapter.id, "状態変更")
    target = services.narrative.create_episode(chapter.id, "対象話")
    character = services.character.create("主人公")
    services.references.add(target.id, "character", character.id)
    services.state.set_state(
        character.id,
        state_episode.id,
        beliefs_json={"belief": "PRIOR_BELIEF"},
    )

    before = services.context.build_episode_context(target.id)
    assert before.participants[0].effective_state is not None
    assert before.participants[0].effective_state.beliefs == {"belief": "PRIOR_BELIEF"}

    services.narrative.reorder_episode(target.id, 1, target.version)
    after = services.context.build_episode_context(target.id)
    serialized = json.dumps(json_value(after), ensure_ascii=False)

    assert after.participants[0].effective_state is None
    assert "PRIOR_BELIEF" not in serialized


def test_future_beliefs_never_leak(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    future = services.narrative.create_episode(chapter.id, "未来話")
    character = services.character.create("主人公")
    services.references.add(target.id, "character", character.id)
    services.state.set_state(
        character.id,
        future.id,
        beliefs_json={"secret": "SECRET_FUTURE_BELIEF"},
    )

    context = services.context.build_episode_context(target.id)
    serialized = json.dumps(json_value(context), ensure_ascii=False)

    assert context.participants[0].effective_state is None
    assert "SECRET_FUTURE_BELIEF" not in serialized


def test_acceptance_helper_detects_deprecated_mapping_payload() -> None:
    assert _has_deprecated({"canon_status": "deprecated"}) is True


def test_future_disclosure_probe_rejects_safe_item_without_disclosure(
    services,
) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    item = services.information.create_information("漏れてはいけない未開示情報")
    fake_context = SimpleNamespace(
        reader_context=ReaderContext(
            known_before_episode=(
                SafeInformationItem(
                    id=item.id,
                    statement=item.statement,
                    truth_status=item.truth_status,
                    canon_status=item.canon_status,
                    importance=item.importance,
                ),
            ),
            reveal_this_episode=(),
        )
    )

    assert _future_disclosure_ok(services.connection, target.id, fake_context) is False


def test_acceptance_gate_seeds_active_attack_probes(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")

    report = run_phase3_acceptance(services.connection, episode_id=target.id)

    assert report.writing_ready is True
    assert all(report.invariants.values())
    assert (
        services.connection.execute(
            "SELECT COUNT(*) FROM episode_world_facts WHERE episode_id = ?",
            (target.id,),
        ).fetchone()[0]
        > 30
    )
    assert (
        services.connection.execute(
            "SELECT COUNT(*) FROM episode_timeline_events WHERE episode_id = ?",
            (target.id,),
        ).fetchone()[0]
        > 30
    )
    information_count = services.connection.execute(
        "SELECT COUNT(*) FROM information_items"
    ).fetchone()[0]
    work_count = services.connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    assert information_count > 50
    assert work_count > 1
    assert (
        services.connection.execute(
            "SELECT COUNT(*) FROM information_items WHERE canon_status = 'deprecated'"
        ).fetchone()[0]
        >= 1
    )
    assert (
        services.connection.execute(
            "SELECT COUNT(*) FROM characters "
            "WHERE private_notes != '' OR profile_json != '{}'"
        ).fetchone()[0]
        >= 1
    )
