from __future__ import annotations

import sqlite3
from pathlib import Path

from novel_core.config import DatabaseConfig
from novel_core.database import default_migration_dir, open_database
from novel_core.document import import_plain_text, serialize_document_json


def create_episode_and_draft(project_dir: Path) -> tuple[int, int]:
    connection = open_database(
        DatabaseConfig(
            db_path=project_dir / "story.db",
            migration_dir=default_migration_dir(),
        )
    )
    try:
        work_id = int(connection.execute("SELECT id FROM works LIMIT 1").fetchone()[0])
        connection.execute(
            "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'C')",
            (work_id,),
        )
        chapter_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO episodes (work_id, chapter_id, position, title) "
            "VALUES (?, ?, 1, 'E')",
            (work_id, chapter_id),
        )
        episode_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO drafts (work_id, episode_id, revision, document_json) "
            "VALUES (?, ?, 1, ?)",
            (work_id, episode_id, serialize_document_json(import_plain_text("本文"))),
        )
        draft_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.commit()
        return episode_id, draft_id
    finally:
        connection.close()


def test_project_episode_capture_creates_style_document(
    client, project_factory
) -> None:
    project_dir = project_factory("draft")
    episode_id, draft_id = create_episode_and_draft(project_dir)

    response = client.post(
        f"/api/v1/projects/draft/style-analysis/project-episodes/{episode_id}/capture",
        json={"draft_id": draft_id},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kind"] == "project_episode_draft"
    assert data["captured_text_revision_id"] == data["current_text_revision_id"]
    assert data["analysis_status"]["basic"]["state"] == "not_analyzed"


def test_project_episode_capture_uses_explicit_draft_error_codes(
    client, project_factory
) -> None:
    project_dir = project_factory("draft-errors")
    episode_id, draft_id = create_episode_and_draft(project_dir)

    missing = client.post(
        f"/api/v1/projects/draft-errors/style-analysis/project-episodes/{episode_id}/capture",
        json={"draft_id": draft_id + 1000},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROJECT_DRAFT_NOT_FOUND"

    db = sqlite3.connect(project_dir / "story.db")
    try:
        work_id = db.execute(
            "SELECT work_id FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO drafts (work_id, episode_id, revision, document_json) "
            "VALUES (?, ?, 2, '{}')",
            (work_id, episode_id),
        )
        invalid_draft_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
        db.commit()
    finally:
        db.close()

    projection_failed = client.post(
        f"/api/v1/projects/draft-errors/style-analysis/project-episodes/{episode_id}/capture",
        json={"draft_id": invalid_draft_id},
    )
    assert projection_failed.status_code == 422
    assert (
        projection_failed.json()["error"]["code"]
        == "PROJECT_DRAFT_TEXT_PROJECTION_FAILED"
    )


def test_lint_endpoint_enqueues_explicit_revision_contract(
    client, project_factory
) -> None:
    project_dir = project_factory("lint")
    episode_id, draft_id = create_episode_and_draft(project_dir)
    capture = client.post(
        f"/api/v1/projects/lint/style-analysis/project-episodes/{episode_id}/capture",
        json={"draft_id": draft_id},
    )
    document_id = capture.json()["data"]["document_id"]
    text_id = capture.json()["data"]["current_text_revision_id"]

    db = sqlite3.connect(project_dir / "story.db")
    try:
        db.execute(
            "INSERT INTO style_structure_revisions "
            "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
            "source_kind, fingerprint) VALUES (?, 1, 'test', 1, 'automatic', ?)",
            (text_id, "a" * 64),
        )
        structure_id = int(db.execute("SELECT last_insert_rowid()").fetchone()[0])
        db.execute(
            "UPDATE style_documents SET current_structure_revision_id = ? WHERE id = ?",
            (structure_id, document_id),
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/api/v1/projects/lint/style-analysis/documents/{document_id}/lint",
        json={
            "text_revision_id": text_id,
            "structure_revision_id": structure_id,
            "profile_id": 1,
            "profile_version_no": 1,
        },
    )

    assert response.status_code == 202
    assert response.json()["data"]["job_type"] == "run_lint"
