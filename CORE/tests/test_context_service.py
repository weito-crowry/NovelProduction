from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from _support import initialize_test_work, json_value

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.services.character_service import CharacterService
from novel_core.services.character_state_service import CharacterStateService
from novel_core.services.context_projection import parse_foreshadowing
from novel_core.services.context_service import ContextService
from novel_core.services.disclosure_service import DisclosureService
from novel_core.services.draft_service import DraftService
from novel_core.services.episode_reference_service import EpisodeReferenceService
from novel_core.services.information_service import InformationService
from novel_core.services.knowledge_service import KnowledgeService
from novel_core.services.narrative_service import NarrativeService
from novel_core.services.relationship_service import RelationshipService
from novel_core.services.timeline_service import TimelineService
from novel_core.services.world_fact_service import WorldFactService


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


def test_context_applies_fixed_bounds_and_previous_draft_projection(services) -> None:
    chapter = services.narrative.create_chapter("章")
    previous = services.narrative.create_episode(chapter.id, "前話", summary="前話要約")
    current = services.narrative.create_episode(chapter.id, "対象話")
    services.narrative.create_episode(chapter.id, "未来話")
    scene = services.narrative.create_scene(previous.id, "前話シーン")
    speaker = services.character.create("話者")
    previous_body = (
        '<p id="earlier" data-ann-emotions="[&quot;焦り&quot;]">前の本文</p>'
        f'<p id="latest" data-np-scene-id="{scene.id}" '
        f'data-np-speaker-id="{speaker.id}">' + "x" * 5001 + "</p>"
    )
    draft = services.drafts.save_draft(
        previous.id,
        html=previous_body,
        metadata_updates={"latest": {"annotations": {"mood": "tense"}}},
    )
    assert draft.revision == 1

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
    assert context.recent_context.previous_draft_context_html == (
        f'<p data-np-type="narration" data-np-scene-id="{scene.id}" '
        f'data-np-speaker-id="{speaker.id}">' + "x" * 5001 + "</p>"
    )
    assert len(context.recent_context.previous_episode_summaries) == 1
    assert context.context_meta["limits"] == {
        "previous_episode_summaries": 2,
        "previous_draft_context_visible_chars": 4000,
        "world_facts_max": 30,
        "timeline_events_max": 30,
        "information_items_max": 50,
    }
    assert context.context_meta["omitted_counts"]["world_facts"] == 10
    assert context.context_meta["omitted_counts"]["timeline_events"] == 10
    assert context.context_meta["returned_counts"]["previous_draft_context_blocks"] == 1
    assert (
        context.context_meta["returned_counts"]["previous_draft_context_visible_chars"]
        == 5001
    )
    assert context.context_meta["truncated"]["previous_draft_context"] is True
    assert ' id="' not in context.recent_context.previous_draft_context_html
    assert "data-np-ann-" not in context.recent_context.previous_draft_context_html
    assert "前の本文" not in context.recent_context.previous_draft_context_html


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
    with pytest.raises(ValueError, match="foreshadowing_notes"):
        parse_foreshadowing("{not valid json")


def test_context_reads_legacy_object_foreshadowing_notes(services) -> None:
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "対象話")
    services.connection.execute(
        "UPDATE episodes SET foreshadowing_notes_json = ? WHERE id = ?",
        ('{"hint":"legacy"}', episode.id),
    )
    services.connection.commit()

    context = services.context.build_episode_context(episode.id)

    assert context.foreshadowing_notes == ({"hint": "legacy"},)


@pytest.mark.parametrize(
    ("stored_value", "expected"),
    [
        ('"legacy hint"', ("legacy hint",)),
        ("null", ()),
    ],
)
def test_context_reads_legacy_scalar_and_null_foreshadowing_notes(
    services, stored_value: str, expected: tuple[object, ...]
) -> None:
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "対象話")
    services.connection.execute(
        "UPDATE episodes SET foreshadowing_notes_json = ? WHERE id = ?",
        (stored_value, episode.id),
    )
    services.connection.commit()

    context = services.context.build_episode_context(episode.id)

    assert context.foreshadowing_notes == expected


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
    services.drafts.save_draft(latest_previous.id, plain_text="直前話本文")

    context = services.context.build_episode_context(target.id)

    assert [
        summary.episode_id
        for summary in context.recent_context.previous_episode_summaries
    ] == [previous.id, latest_previous.id]
    assert context.recent_context.previous_draft_context_html == (
        '<p data-np-type="narration">直前話本文</p>'
    )


def test_context_has_empty_previous_draft_projection_when_no_draft(services) -> None:
    chapter = services.narrative.create_chapter("章")
    services.narrative.create_episode(chapter.id, "前話")
    current = services.narrative.create_episode(chapter.id, "対象話")

    context = services.context.build_episode_context(current.id)

    assert context.recent_context.previous_draft_context_html == ""
    assert context.context_meta["returned_counts"]["previous_draft_context_blocks"] == 0
    assert (
        context.context_meta["returned_counts"]["previous_draft_context_visible_chars"]
        == 0
    )
