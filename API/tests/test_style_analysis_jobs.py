import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from novel_core.config import DatabaseConfig
from novel_core.database import default_migration_dir, open_database
from novel_core.style_analysis.runtime_models import JobRecord

from novel_api.app import create_app
from novel_api.config import ApiSettings
from novel_api.project_registry import ProjectRegistry
from novel_api.style_analysis.job_service import StyleJobService
from novel_api.style_analysis.job_worker import StyleAnalysisWorker


def insert_job_row(project_db: Path, *, status: str, job_type: str) -> int:
    connection = open_database(
        DatabaseConfig(db_path=project_db, migration_dir=default_migration_dir())
    )
    try:
        cursor = connection.execute(
            "INSERT INTO style_jobs (job_type, status) VALUES (?, ?)",
            (job_type, status),
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid
    finally:
        connection.close()


def select_job_statuses(project_db: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(project_db)
    try:
        return tuple(
            row[0]
            for row in connection.execute("SELECT status FROM style_jobs ORDER BY id")
        )
    finally:
        connection.close()


def read_job(project_db: Path, job_id: int) -> JobRecord:
    service = StyleJobService(data_root=project_db.parent.parent)
    job = service.get(project_db.parent.name, job_id)
    assert job is not None
    return job


def test_enqueue_commits_before_worker_notification(data_root: Path) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    observed: list[str] = []
    service = StyleJobService(data_root=data_root, notify=observed.append)

    job = service.enqueue(project_id="demo", job_type="analyze_document", payload={})

    assert job.status == "queued"
    assert observed == ["demo"]
    assert select_job_statuses(data_root / "demo" / "story.db") == ("queued",)


def test_cancel_queued_job_and_request_cancel_for_running_job(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    service = StyleJobService(data_root=data_root)
    queued = service.enqueue(project_id="demo", job_type="analyze_document", payload={})
    cancelled = service.cancel("demo", queued.id)
    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None

    running_id = insert_job_row(
        data_root / "demo" / "story.db",
        status="running",
        job_type="analyze_document",
    )
    running = service.cancel("demo", running_id)
    assert running.status == "running"
    assert running.cancel_requested == 1


def test_retry_creates_new_queued_job_and_preserves_terminal_original(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    service = StyleJobService(data_root=data_root)
    original_id = insert_job_row(
        data_root / "demo" / "story.db",
        status="failed",
        job_type="analyze_document",
    )

    retried = service.retry("demo", original_id)

    assert retried.id != original_id
    assert retried.status == "queued"
    assert json.loads(retried.payload_json) == {"retry_of_job_id": original_id}
    assert read_job(data_root / "demo" / "story.db", original_id).status == "failed"


@pytest.mark.parametrize("status", ["queued", "running"])
def test_retry_rejects_non_terminal_job(data_root: Path, status: str) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    service = StyleJobService(data_root=data_root)
    job_id = insert_job_row(
        data_root / "demo" / "story.db",
        status=status,
        job_type="analyze_document",
    )

    with pytest.raises(ValueError, match="JOB_NOT_TERMINAL"):
        service.retry("demo", job_id)


def test_partial_terminal_status_is_limited_to_analysis_jobs(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    service = StyleJobService(data_root=data_root)
    lint_id = insert_job_row(
        data_root / "demo" / "story.db",
        status="queued",
        job_type="run_lint",
    )

    with pytest.raises(ValueError, match="PARTIAL_STATUS_NOT_ALLOWED"):
        service.set_status("demo", lint_id, "partial")

    document_id = insert_job_row(
        data_root / "demo" / "story.db",
        status="queued",
        job_type="analyze_document",
    )
    assert service.set_status("demo", document_id, "partial").status == "partial"


def test_start_recovers_interrupted_running_jobs_and_keeps_queued_jobs(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    project_db = data_root / "demo" / "story.db"
    insert_job_row(project_db, status="running", job_type="analyze_document")
    insert_job_row(project_db, status="queued", job_type="analyze_reference_work")
    worker = StyleAnalysisWorker(data_root=data_root)

    worker.start()
    try:
        assert select_job_statuses(project_db) == ("failed", "queued")
    finally:
        worker.stop()


def test_worker_drain_uses_project_fifo_and_injected_executor(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    project_db = data_root / "demo" / "story.db"
    first_id = insert_job_row(project_db, status="queued", job_type="analyze_document")
    second_id = insert_job_row(
        project_db, status="queued", job_type="analyze_reference_work"
    )
    observed: list[int] = []

    def executor(_connection: sqlite3.Connection, job: JobRecord) -> None:
        observed.append(job.id)

    worker = StyleAnalysisWorker(data_root=data_root, executor=executor)
    worker.notify("demo")

    assert worker.drain_once() is True
    assert worker.drain_once() is True
    assert observed == [first_id, second_id]
    assert select_job_statuses(project_db) == ("succeeded", "succeeded")


def test_app_lifespan_owns_one_worker_instance(data_root: Path) -> None:
    app = create_app(ApiSettings(data_root=data_root))
    worker = app.state.style_analysis_worker
    assert worker.is_running is False

    with TestClient(app):
        assert app.state.style_analysis_worker is worker
        assert worker.is_running is True

    assert worker.is_running is False
