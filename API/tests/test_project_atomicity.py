from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import read_project_metadata, read_working_title

import novel_api.project_registry as project_registry_module
from novel_api.project_registry import ProjectConflictError, ProjectRegistry

_UTC = timezone(timedelta(0))


def test_create_initializes_story_db_and_metadata_atomically(data_root: Path) -> None:
    registry = ProjectRegistry(data_root)

    summary = registry.create("Winter Tokyo", project_id="winter-tokyo")

    assert summary.project_id == "winter-tokyo"
    assert summary.status == "active"
    assert summary.metadata_state == "ok"
    assert summary.working_title == "Winter Tokyo"
    assert summary.health == "ok"

    project_dir = data_root / "winter-tokyo"
    metadata = read_project_metadata(project_dir)
    timestamp = metadata["created_at"]
    assert metadata == {
        "project_id": "winter-tokyo",
        "status": "active",
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    assert read_working_title(project_dir / "story.db") == "Winter Tokyo"

    connection = sqlite3.connect(project_dir / "story.db")
    try:
        versions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
        work_count = connection.execute("SELECT COUNT(*) FROM works").fetchone()
    finally:
        connection.close()

    assert versions == (
        "001_initial.sql",
        "002_search.sql",
        "003_narrative.sql",
        "004_drafts.sql",
        "005_structured_drafts.sql",
        "006_style_analysis_foundation.sql",
        "007_style_analysis_semantics.sql",
        "008_style_analysis_corpus_profile.sql",
    )
    assert work_count == (1,)


def test_create_generates_timestamp_ids_and_collision_suffixes(
    data_root: Path, monkeypatch
) -> None:
    fixed_now = datetime(2026, 8, 28, 5, 38, 12, tzinfo=_UTC)
    monkeypatch.setattr(project_registry_module, "_utc_now", lambda: fixed_now)
    registry = ProjectRegistry(data_root)

    first = registry.create("冬東京")
    second = registry.create("冬東京")
    third = registry.create("冬東京")

    assert first.project_id == "project-20260828-053812"
    assert second.project_id == "project-20260828-053812-2"
    assert third.project_id == "project-20260828-053812-3"
    assert read_working_title(data_root / third.project_id / "story.db") == "冬東京"


def test_create_rejects_duplicate_and_invalid_ids_without_escaping_data_root(
    data_root: Path,
) -> None:
    registry = ProjectRegistry(data_root)
    registry.create("Original", project_id="winter-tokyo")

    with pytest.raises(ProjectConflictError):
        registry.create("Duplicate", project_id="winter-tokyo")

    for invalid_project_id in (
        "../escape",
        r"..\escape",
        "alpha/beta",
        "alpha\\beta",
        "alpha beta",
        "-alpha",
        "alpha-",
        "A",
        "あ",
        "a" * 65,
    ):
        with pytest.raises(ValueError):
            registry.create("Invalid", project_id=invalid_project_id)

    visible_dirs = sorted(
        path.name for path in data_root.iterdir() if not path.name.startswith(".")
    )
    assert visible_dirs == ["winter-tokyo"]
    assert read_working_title(data_root / "winter-tokyo" / "story.db") == "Original"


def test_create_cleans_staging_and_lock_when_integrity_check_fails(
    data_root: Path, monkeypatch
) -> None:
    registry = ProjectRegistry(data_root)
    monkeypatch.setattr(
        project_registry_module,
        "assert_database_integrity",
        lambda connection: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        registry.create("Broken Project", project_id="broken-project")

    assert not (data_root / "broken-project").exists()
    assert registry.list() == []
    locks_dir = data_root / ".locks"
    staging_dir = data_root / ".staging"
    assert not any(locks_dir.iterdir()) if locks_dir.exists() else True
    assert not any(staging_dir.iterdir()) if staging_dir.exists() else True


def test_create_reports_conflict_and_cleans_up_when_rename_loses_race(
    data_root: Path, monkeypatch
) -> None:
    registry = ProjectRegistry(data_root)

    def lose_race(source: Path, target: Path) -> Path:
        target.mkdir()
        raise FileExistsError(target)

    monkeypatch.setattr(Path, "rename", lose_race)

    with pytest.raises(ProjectConflictError):
        registry.create("Racing Project", project_id="racing-project")

    assert (data_root / "racing-project").is_dir()
    assert list((data_root / ".locks").iterdir()) == []
    assert list((data_root / ".staging").iterdir()) == []


def test_set_status_repairs_invalid_metadata_with_atomic_replace(
    data_root: Path, project_factory, monkeypatch
) -> None:
    fixed_now = datetime(2026, 8, 28, 9, 0, 0, tzinfo=_UTC)
    monkeypatch.setattr(project_registry_module, "_utc_now", lambda: fixed_now)
    project_dir = project_factory(
        "repair-me", working_title="Repair Me", metadata="{bad json"
    )
    metadata_path = project_dir / "project.json"
    original_bytes = metadata_path.read_bytes()
    registry = ProjectRegistry(data_root)

    updated = registry.set_status("repair-me", "archived")

    assert updated.status == "archived"
    assert updated.metadata_state == "ok"
    assert updated.created_at == "2026-08-28T09:00:00Z"
    assert updated.updated_at == "2026-08-28T09:00:00Z"
    assert metadata_path.read_bytes() != original_bytes
    assert read_project_metadata(project_dir) == {
        "project_id": "repair-me",
        "status": "archived",
        "created_at": "2026-08-28T09:00:00Z",
        "updated_at": "2026-08-28T09:00:00Z",
    }


def test_set_status_preserves_valid_created_at_from_otherwise_invalid_metadata(
    data_root: Path, project_factory, monkeypatch
) -> None:
    fixed_now = datetime(2026, 8, 28, 9, 0, 0, tzinfo=_UTC)
    monkeypatch.setattr(project_registry_module, "_utc_now", lambda: fixed_now)
    project_factory(
        "repair-me",
        metadata={
            "project_id": "repair-me",
            "status": "invalid",
            "created_at": "2026-08-20T01:02:03Z",
            "updated_at": "invalid",
        },
    )

    updated = ProjectRegistry(data_root).set_status("repair-me", "archived")

    assert updated.created_at == "2026-08-20T01:02:03Z"
    assert updated.updated_at == "2026-08-28T09:00:00Z"


def test_set_status_replace_failure_preserves_original_metadata(
    data_root: Path, project_factory, monkeypatch
) -> None:
    project_dir = project_factory(
        "safe-project",
        metadata={
            "project_id": "safe-project",
            "status": "active",
            "created_at": "2026-08-20T01:02:03Z",
            "updated_at": "2026-08-20T01:02:03Z",
        },
    )
    metadata_path = project_dir / "project.json"
    original_bytes = metadata_path.read_bytes()
    monkeypatch.setattr(
        project_registry_module.os,
        "replace",
        lambda source, destination: (_ for _ in ()).throw(
            RuntimeError("replace failed")
        ),
    )

    with pytest.raises(RuntimeError, match="replace failed"):
        ProjectRegistry(data_root).set_status("safe-project", "archived")

    assert metadata_path.read_bytes() == original_bytes
    assert list(project_dir.glob(".project.json.*.tmp")) == []
