from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from novel_core.config import DatabaseConfig
from novel_core.database import default_migration_dir, open_database
from novel_core.document import import_plain_text, serialize_document_json
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.profile_service import ProfileService

from novel_api.style_analysis.execution import execute_style_job
from novel_api.style_analysis.job_service import StyleJobService


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


def test_lint_job_keeps_progress_legal_when_selector_is_unavailable(
    client, project_factory, monkeypatch
) -> None:
    project_dir = project_factory("lint-progress")
    episode_id, draft_id = create_episode_and_draft(project_dir)
    capture = client.post(
        f"/api/v1/projects/lint-progress/style-analysis/project-episodes/{episode_id}/capture",
        json={"draft_id": draft_id},
    )
    captured = capture.json()["data"]
    document_id = int(captured["document_id"])
    text_id = int(captured["current_text_revision_id"])
    connection = sqlite3.connect(project_dir / "story.db")
    try:
        connection.execute(
            "INSERT INTO style_structure_revisions "
            "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
            "source_kind, fingerprint) VALUES (?, 1, 'test', 1, 'automatic', ?)",
            (text_id, "b" * 64),
        )
        structure_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        connection.execute(
            "INSERT INTO style_scenes "
            "(structure_revision_id, order_index, start_cp, end_cp) "
            "VALUES (?, 1, 0, 2)",
            (structure_id,),
        )
        int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "UPDATE style_documents SET current_structure_revision_id = ? WHERE id = ?",
            (structure_id, document_id),
        )
        metric_run_id = AnalysisRunRepository(connection).insert_run(
            document_id=document_id,
            analyzer_id="style-metrics-basic",
            analyzer_version=1,
            text_revision_id=text_id,
            structure_revision_id=structure_id,
            status="succeeded",
            fingerprint="c" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        connection.execute(
            "INSERT INTO style_measurements "
            "(analysis_run_id, structure_revision_id, target_type, target_id, "
            "metric_name, metric_version, value_int, sample_count) "
            "VALUES (?, ?, 'document', ?, 'text.char_count', 1, 15, 1)",
            (metric_run_id, structure_id, document_id),
        )
        profile = ProfileService(connection).create_manual(
            name="Progress Profile",
            rules=(
                {
                    "target_scope": "scene",
                    "scope_selector": {"function": ["exposition"]},
                    "metric_name": "text.char_count",
                    "metric_version": 1,
                    "preferred_value": 15,
                    "min_value": 10,
                    "max_value": 20,
                    "weight": 1.0,
                    "enabled": True,
                    "severity_policy": "standard",
                },
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "text.char_count",
                    "metric_version": 1,
                    "preferred_value": 15,
                    "min_value": 10,
                    "max_value": 20,
                    "weight": 1.0,
                    "enabled": True,
                    "severity_policy": "standard",
                },
            ),
        )
        payload = json.dumps(
            {
                "document_id": document_id,
                "text_revision_id": text_id,
                "structure_revision_id": structure_id,
                "profile_id": profile.profile.id,
                "profile_version_no": profile.version.version_no,
            }
        )
        cursor = connection.execute(
            "INSERT INTO style_jobs (job_type, payload_json, status) "
            "VALUES ('run_lint', ?, 'running')",
            (payload,),
        )
        assert cursor.lastrowid is not None
        job_id = int(cursor.lastrowid)
        connection.commit()
        row = connection.execute(
            "SELECT id, job_type, payload_json, status, cancel_requested, "
            "progress_current, progress_total, result_json, warning_json, created_at, "
            "started_at, finished_at, error_code, error_message, version "
            "FROM style_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert row is not None
        job = StyleJobService._record_from_row(row)
        monkeypatch.setattr(
            CurrentRunResolver,
            "resolve",
            lambda self, *args: (
                SimpleNamespace(id=metric_run_id)
                if args[-1] == "style-metrics-basic"
                else None
            ),
        )

        execute_style_job(
            connection,
            job,
            model_client=None,
            model_provider=None,
            model_id=None,
        )
        status, current, total, result_json = connection.execute(
            "SELECT status, progress_current, progress_total, result_json "
            "FROM style_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    finally:
        connection.close()

    assert status == "succeeded"
    assert 0 <= current <= total
    assert (current, total) == (2, 2)
    result = json.loads(result_json)
    assert result["applicable_rule_count"] == 2
    assert result["missing_rule_count"] == 1
