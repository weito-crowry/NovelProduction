from __future__ import annotations

from pathlib import Path

import pytest
from novel_core.services.canon_service import CanonService
from novel_core.services.information_service import InformationService
from novel_core.services.narrative_service import NarrativeService

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import CanonReasonRequired


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[2] / "CORE" / "migrations",
        )
    )


@pytest.fixture
def services(tmp_path: Path):
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)
    try:
        yield type(
            "Services",
            (),
            {
                "connection": connection,
                "canon": CanonService(connection),
                "information": InformationService(connection),
                "narrative": NarrativeService(connection),
            },
        )()
    finally:
        connection.close()


def test_canon_status_set_supports_phase2_entity_types(services) -> None:
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "話")
    scene = services.narrative.create_scene(episode.id, "場面")
    item = services.information.create_information("情報")

    decisions = (
        services.canon.set_canon_status("chapter", chapter.id, "canon", 1, "採用"),
        services.canon.set_canon_status("episode", episode.id, "canon", 1, "採用"),
        services.canon.set_canon_status("scene", scene.id, "canon", 1, "採用"),
        services.canon.set_canon_status(
            "information_item", item.id, "canon", 1, "採用"
        ),
    )

    assert [decision.changes[0].entity_type for decision in decisions] == [
        "chapter",
        "episode",
        "scene",
        "information_item",
    ]


def test_phase2_canonical_content_updates_cannot_bypass_reason(services) -> None:
    chapter = services.narrative.create_chapter("章")
    episode = services.narrative.create_episode(chapter.id, "話")
    scene = services.narrative.create_scene(episode.id, "場面")
    item = services.information.create_information("情報")
    services.canon.set_canon_status("chapter", chapter.id, "canon", 1, "採用")
    services.canon.set_canon_status("episode", episode.id, "canon", 1, "採用")
    services.canon.set_canon_status("scene", scene.id, "canon", 1, "採用")
    services.canon.set_canon_status("information_item", item.id, "canon", 1, "採用")

    with pytest.raises(CanonReasonRequired):
        services.narrative.update_chapter(chapter.id, 2, title="改訂")
    with pytest.raises(CanonReasonRequired):
        services.narrative.update_episode(episode.id, 2, title="改訂")
    with pytest.raises(CanonReasonRequired):
        services.narrative.update_scene(scene.id, 2, title="改訂")
    with pytest.raises(CanonReasonRequired):
        services.information.update_information(item.id, 2, statement="改訂")

    assert services.narrative.get_chapter(chapter.id).title == "章"
    assert services.information.get_information(item.id).statement == "情報"


def test_phase2_status_update_uses_canon_policy_and_audit(services) -> None:
    chapter = services.narrative.create_chapter("章")
    updated = services.narrative.update_chapter(
        chapter.id, chapter.version, canon_status="canon", reason="採用"
    )
    assert (updated.canon_status, updated.version) == ("canon", 2)
    assert services.canon.get_decision(1).changes[0].entity_type == "chapter"

    with pytest.raises(CanonReasonRequired):
        services.narrative.update_chapter(
            chapter.id, updated.version, canon_status="deprecated"
        )
    restored = services.narrative.update_chapter(
        chapter.id,
        updated.version,
        canon_status="deprecated",
        reason="撤回",
    )
    draft = services.narrative.update_chapter(
        chapter.id, restored.version, canon_status="draft"
    )
    assert draft.canon_status == "draft"
    with pytest.raises(CanonReasonRequired):
        services.narrative.update_chapter(
            chapter.id, draft.version, canon_status="canon"
        )
