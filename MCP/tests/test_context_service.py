from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.character_state_service import CharacterStateService
from novel_mcp.services.context_service import ContextService
from novel_mcp.services.disclosure_service import DisclosureService
from novel_mcp.services.draft_service import DraftService
from novel_mcp.services.episode_reference_service import EpisodeReferenceService
from novel_mcp.services.information_service import InformationService
from novel_mcp.services.knowledge_service import KnowledgeService
from novel_mcp.services.narrative_service import NarrativeService
from novel_mcp.services.relationship_service import RelationshipService
from novel_mcp.services.timeline_service import TimelineService
from novel_mcp.services.world_fact_service import WorldFactService
from novel_mcp.tool_errors import json_value


@pytest.fixture
def services(tmp_path: Path):
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "Phase 3")
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
            drafts=DraftService(connection),
            information=InformationService(connection),
            knowledge=KnowledgeService(connection),
            narrative=NarrativeService(connection),
            references=EpisodeReferenceService(connection),
            relationship=RelationshipService(connection),
            timeline=TimelineService(connection),
            world=WorldFactService(connection),
        )
    finally:
        connection.close()


def test_context_applies_fixed_bounds_and_previous_draft_tail(services) -> None:
    chapter = services.narrative.create_chapter("章")
    previous = services.narrative.create_episode(chapter.id, "前話", summary="前話要約")
    current = services.narrative.create_episode(chapter.id, "対象話")
    services.narrative.create_episode(chapter.id, "未来話")
    parent = None
    previous_body = "x" * 5001
    draft = services.drafts.save_draft(
        previous.id, previous_body, expected_parent_draft_id=parent
    )
    assert draft.body == previous_body

    for index in range(40):
        fact = services.world.create(
            f"世界設定 {index}",
            topic_key=f"fact-{index}",
            title=f"設定 {index}",
            importance=index,
        )
        services.references.add(current.id, "world_fact", fact.id)
        event = services.timeline.create_event(
            title=f"イベント {index}", importance=index
        )
        services.references.add(current.id, "timeline_event", event.id)

    context = services.context.build_episode_context(current.id)

    assert len(context.world_facts) == 30
    assert len(context.timeline_events) == 30
    assert context.recent_context.previous_draft_tail == "x" * 4000
    assert len(context.recent_context.previous_episode_summaries) == 1
    assert context.context_meta["limits"] == {
        "previous_episode_summaries": 2,
        "previous_draft_tail_chars": 4000,
        "world_facts_max": 30,
        "timeline_events_max": 30,
        "information_items_max": 50,
    }
    assert context.context_meta["omitted_counts"]["world_facts"] == 10
    assert context.context_meta["omitted_counts"]["timeline_events"] == 10
    assert context.context_meta["truncated"]["previous_draft_tail"] is True


def test_context_composes_effective_participant_state_relationship_and_knowledge(
    services,
) -> None:
    chapter = services.narrative.create_chapter("章")
    current = services.narrative.create_episode(chapter.id, "対象話")
    character = services.character.create("主人公")
    other = services.character.create("相手")
    information = services.information.create_information("既知の事実")
    services.references.add(current.id, "character", character.id, role="viewpoint")
    services.references.add(current.id, "character", other.id)
    services.knowledge.set_character_knowledge(
        character.id, information.id, current.id, "knows"
    )
    services.disclosure.set_reader_disclosure(information.id, current.id)
    services.state.set_state(
        character.id,
        current.id,
        physical_state="負傷",
        emotional_state="警戒",
    )
    services.relationship.create(
        character.id, other.id, "ally", "協力関係", valid_from_episode_id=current.id
    )

    context = services.context.build_episode_context(current.id)

    participant = context.participants[0]
    assert participant.profile.display_name == "主人公"
    assert participant.effective_state.physical_state == "負傷"
    assert participant.effective_state.emotional_state == "警戒"
    assert participant.effective_relationships[0].relationship_type == "ally"
    assert participant.known_information[0].statement == "既知の事実"


def test_context_is_stable_and_write_free(services) -> None:
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(
        chapter.id, "対象話", foreshadowing_notes=["伏線"]
    )
    statements: list[str] = []
    services.connection.set_trace_callback(statements.append)
    try:
        first = json_value(services.context.build_episode_context(episode.id))
        second = json_value(services.context.build_episode_context(episode.id))
    finally:
        services.connection.set_trace_callback(None)

    assert first == second
    assert first["foreshadowing_notes"] == ["伏線"]
    assert not any(
        statement.lstrip()
        .upper()
        .startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"))
        for statement in statements
    )


def test_context_rejects_malformed_foreshadowing_notes(services) -> None:
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "対象話")
    services.connection.execute(
        "UPDATE episodes SET foreshadowing_notes_json = ? WHERE id = ?",
        (json.dumps({"not": "an array"}), episode.id),
    )
    services.connection.commit()

    with pytest.raises(ValueError, match="foreshadowing_notes"):
        services.context.build_episode_context(episode.id)


def test_context_information_cap_applies_to_participant_known_information(
    services,
) -> None:
    chapter = services.narrative.create_chapter("章")
    previous = services.narrative.create_episode(chapter.id, "前話")
    target = services.narrative.create_episode(chapter.id, "対象話")
    character = services.character.create("主人公")
    services.references.add(target.id, "character", character.id)
    for index in range(70):
        item = services.information.create_information(
            f"reader-safe information {index}", importance=index
        )
        services.disclosure.set_reader_disclosure(item.id, previous.id)
        services.knowledge.set_character_knowledge(
            character.id, item.id, previous.id, "knows"
        )

    context = services.context.build_episode_context(target.id)

    assert len(context.reader_context.known_before_episode) == 50
    assert len(context.participants[0].known_information) == 50
    assert context.context_meta["omitted_counts"]["information_items"] == 20


def test_context_previous_data_follows_reordered_narrative_order(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    previous = services.narrative.create_episode(chapter.id, "前話", summary="前話要約")
    latest_previous = services.narrative.create_episode(
        chapter.id, "直前話", summary="直前要約"
    )
    services.narrative.reorder_episode(target.id, 3, target.version)
    services.drafts.save_draft(latest_previous.id, "直前話本文")

    context = services.context.build_episode_context(target.id)

    assert [
        summary.episode_id
        for summary in context.recent_context.previous_episode_summaries
    ] == [previous.id, latest_previous.id]
    assert context.recent_context.previous_draft_tail == "直前話本文"
