from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _support import initialize_test_work, json_value

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import NovelMcpError
from novel_core.services.character_service import CharacterService
from novel_core.services.disclosure_service import DisclosureService
from novel_core.services.episode_reference_service import EpisodeReferenceService
from novel_core.services.information_service import InformationService
from novel_core.services.narrative_service import NarrativeService
from novel_core.services.outline_service import OutlineService
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
            narrative=NarrativeService(connection),
            character=CharacterService(connection),
            disclosure=DisclosureService(connection),
            references=EpisodeReferenceService(connection),
            information=InformationService(connection),
            outline=OutlineService(connection),
            timeline=TimelineService(connection),
            world=WorldFactService(connection),
        )
    finally:
        connection.close()


def test_outline_returns_target_only_in_narrative_order(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    future = services.narrative.create_episode(chapter.id, "未来話")
    services.narrative.create_scene(target.id, "Scene 2")
    services.narrative.create_scene(target.id, "Scene 1")
    services.narrative.create_scene(future.id, "未来Scene")

    outline = services.outline.get_episode_outline(target.id)

    assert outline.episode.id == target.id
    assert [scene.title for scene in outline.scenes] == ["Scene 2", "Scene 1"]
    assert all(scene.episode_id == target.id for scene in outline.scenes)


def test_outline_uses_safe_projections_and_disclosure_boundary(services) -> None:
    chapter = services.narrative.create_chapter("章")
    target = services.narrative.create_episode(chapter.id, "対象話")
    future = services.narrative.create_episode(chapter.id, "未来話")
    character = services.character.create(
        display_name="主人公",
        character_key="hero",
        description="安全な説明",
        private_notes="SECRET_PRIVATE_NOTE",
        profile_json=json.dumps({"secret": "SECRET_PROFILE_JSON"}),
        death_date="2200-01-01",
    )
    world_fact = services.world.create(
        "安全な世界設定",
        topic_key="setting",
        title="場所",
        details_json=json.dumps({"secret": "SECRET_DETAILS_JSON"}),
    )
    timeline_event = services.timeline.create_event(
        title="歴史イベント", description="安全な説明"
    )
    known = services.information.create_information(
        "対象話で開示する情報", notes_json={"secret": "SECRET_NOTES_JSON"}
    )
    protected = services.information.create_information(
        "未来の秘密本文",
        authoring_guard="未来の秘密本文を漏らさない",
    )
    services.disclosure.set_reader_disclosure(known.id, target.id)
    services.disclosure.set_reader_disclosure(protected.id, future.id)
    for reference_type, target_id in (
        ("character", character.id),
        ("world_fact", world_fact.id),
        ("timeline_event", timeline_event.id),
        ("information", known.id),
        ("information", protected.id),
    ):
        services.references.add(target.id, reference_type, target_id)

    outline = services.outline.get_episode_outline(target.id)
    serialized = json.dumps(json_value(outline), ensure_ascii=False)

    assert outline.participants[0].profile.display_name == "主人公"
    assert not hasattr(outline.participants[0].profile, "private_notes")
    assert not hasattr(outline.participants[0].profile, "profile_json")
    assert not hasattr(outline.participants[0].profile, "death_date")
    assert outline.references.world_facts[0].statement == "安全な世界設定"
    assert not hasattr(outline.references.world_facts[0], "details_json")
    assert outline.references.timeline_events[0].title == "歴史イベント"
    assert [item.statement for item in outline.references.information] == [
        "対象話で開示する情報"
    ]
    assert outline.protected_information_guards[0].information_item_id == protected.id
    assert "未来の秘密本文" not in serialized
    assert "SECRET_PRIVATE_NOTE" not in serialized
    assert "SECRET_PROFILE_JSON" not in serialized
    assert "SECRET_DETAILS_JSON" not in serialized
    assert "SECRET_NOTES_JSON" not in serialized


def test_outline_rejects_deprecated_target(services) -> None:
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "対象話")
    canonical = services.narrative.update_episode(
        episode.id, episode.version, canon_status="canon", reason="採用"
    )
    services.narrative.update_episode(
        episode.id, canonical.version, canon_status="deprecated", reason="撤回"
    )

    with pytest.raises(NovelMcpError, match="DEPRECATED_CANON_FORBIDDEN"):
        services.outline.get_episode_outline(episode.id)
