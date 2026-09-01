import json
import sqlite3
from pathlib import Path
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient
from novel_core.config import DatabaseConfig
from novel_core.database import default_migration_dir, open_database
from novel_core.style_analysis.model_contracts import ModelRequest
from novel_core.style_analysis.runtime_models import JobRecord

from novel_api.app import create_app
from novel_api.config import ApiSettings
from novel_api.project_registry import ProjectRegistry
from novel_api.service_container import ProjectDescriptor, ProjectTarget
from novel_api.style_analysis import job_service as job_service_module
from novel_api.style_analysis import job_worker as job_worker_module
from novel_api.style_analysis.execution import execute_style_job
from novel_api.style_analysis.ingestion_service import import_source
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


class _WorkFakeModel:
    def complete_json(self, request: ModelRequest) -> dict[str, object]:
        if request.prompt_id == "style.entity_mentions":
            return {"mentions": []}
        if request.prompt_id == "style.term_candidates":
            return {"terms": []}
        if request.prompt_id == "style.speaker_attribution":
            return {
                "speaker_entity_id": None,
                "confidence": 0.0,
                "evidence_block_ids": [],
                "reason_code": "unknown",
            }
        if request.prompt_id == "style.pov":
            return {"pov_mode": "unclear", "pov_entity_id": None, "confidence": 0.1}
        if request.prompt_id == "style.scene_boundary":
            return {"boundaries": []}
        if request.prompt_id == "style.scene_semantics":
            return {
                "function": [{"label": "daily", "confidence": 0.9}],
                "tone": [{"label": "calm", "confidence": 0.9}],
                "pace": {"label": "medium", "confidence": 0.9},
                "information_load": {"label": "low", "confidence": 0.9},
                "interaction": {"label": "dialogue", "confidence": 0.9},
            }
        if request.prompt_id == "style.block_semantic":
            return {"label": "description", "confidence": 0.9}
        raise AssertionError(request.prompt_id)


def test_fresh_reference_work_full_analysis_does_not_nest_transactions(
    data_root: Path,
) -> None:
    registry = ProjectRegistry(data_root)
    registry.create("Reference", project_id="reference")
    project_dir = data_root / "reference"
    target = ProjectTarget(
        project_id="reference",
        descriptor=ProjectDescriptor(
            project_dir=project_dir, story_db=project_dir / "story.db"
        ),
    )
    imported = import_source(
        target,
        source_type="text",
        filename="reference.txt",
        payload="Episode 1\n\n本文。".encode(),
        media_type="text/plain",
    )
    connection = open_database(
        DatabaseConfig(
            db_path=project_dir / "story.db", migration_dir=default_migration_dir()
        )
    )
    try:
        cursor = connection.execute(
            "INSERT INTO style_jobs (job_type, payload_json, status) "
            "VALUES ('analyze_reference_work', ?, 'running')",
            (
                json.dumps(
                    {"reference_work_id": imported.reference_work_id, "preset": "full"}
                ),
            ),
        )
        assert cursor.lastrowid is not None
        connection.commit()
        row = connection.execute(
            "SELECT id, job_type, payload_json, status, cancel_requested, "
            "progress_current, progress_total, result_json, warning_json, created_at, "
            "started_at, finished_at, error_code, error_message, version "
            "FROM style_jobs WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        assert row is not None
        job = StyleJobService._record_from_row(row)

        execute_style_job(
            connection,
            job,
            model_client=_WorkFakeModel(),
            model_provider="test",
            model_id="fake",
        )

        assert connection.execute(
            "SELECT status FROM style_jobs WHERE id = ?", (job.id,)
        ).fetchone() == ("succeeded",)
        assert connection.execute(
            "SELECT COUNT(*) FROM style_structure_revisions"
        ).fetchone() == (1,)
    finally:
        connection.close()


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


def test_cancel_starts_write_transaction_before_read(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    service = StyleJobService(data_root=data_root)
    job = service.enqueue(project_id="demo", job_type="analyze_document", payload={})
    statements: list[str] = []
    original_open_database = job_service_module.open_database

    def open_with_trace(config: DatabaseConfig) -> sqlite3.Connection:
        connection = original_open_database(config)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(job_service_module, "open_database", open_with_trace)

    assert service.cancel("demo", job.id).status == "cancelled"

    begin_index = statements.index("BEGIN IMMEDIATE")
    read_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("SELECT id, job_type") and "WHERE id =" in statement
    )
    assert begin_index < read_index


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


def test_retry_notifies_after_commit_and_preserves_terminal_original(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    project_db = data_root / "demo" / "story.db"
    original_id = insert_job_row(
        project_db, status="failed", job_type="analyze_document"
    )
    observed: list[str] = []

    def notify(project_id: str) -> None:
        observed.append(project_id)
        assert select_job_statuses(project_db) == ("failed", "queued")

    service = StyleJobService(data_root=data_root, notify=notify)
    retried = service.retry("demo", original_id)

    assert observed == ["demo"]
    assert read_job(data_root / "demo" / "story.db", original_id).status == "failed"
    assert retried.status == "queued"
    assert json.loads(retried.payload_json) == {"retry_of_job_id": original_id}


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


def test_worker_preserves_executor_terminal_statuses(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    project_db = data_root / "demo" / "story.db"
    partial_id = insert_job_row(
        project_db, status="queued", job_type="analyze_document"
    )
    failed_id = insert_job_row(project_db, status="queued", job_type="analyze_document")

    def executor(connection: sqlite3.Connection, job: JobRecord) -> None:
        status = "partial" if job.id == partial_id else "failed"
        connection.execute(
            "UPDATE style_jobs SET status = ? WHERE id = ?", (status, job.id)
        )

    worker = StyleAnalysisWorker(data_root=data_root, executor=executor)
    worker.notify("demo")

    assert worker.drain_once() is True
    assert worker.drain_once() is True
    assert read_job(project_db, partial_id).status == "partial"
    assert read_job(project_db, failed_id).status == "failed"


def test_worker_does_not_execute_cancelled_job(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    project_db = data_root / "demo" / "story.db"
    job_id = insert_job_row(project_db, status="queued", job_type="analyze_document")
    service = StyleJobService(data_root=data_root)
    assert service.cancel("demo", job_id).status == "cancelled"
    executed: list[int] = []

    def executor(_connection: sqlite3.Connection, job: JobRecord) -> None:
        executed.append(job.id)

    worker = StyleAnalysisWorker(data_root=data_root, executor=executor)
    worker.notify("demo")

    assert worker.drain_once() is False
    assert executed == []
    assert read_job(project_db, job_id).status == "cancelled"


def test_service_cancel_after_worker_claim_requests_cancellation(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    project_db = data_root / "demo" / "story.db"
    job_id = insert_job_row(project_db, status="queued", job_type="analyze_document")
    service = StyleJobService(data_root=data_root)
    executor_started = Event()
    release_executor = Event()
    drain_results: list[bool] = []

    def executor(_connection: sqlite3.Connection, job: JobRecord) -> None:
        assert job.id == job_id
        executor_started.set()
        assert release_executor.wait(timeout=5)

    worker = StyleAnalysisWorker(data_root=data_root, executor=executor)
    worker.notify("demo")
    drain_thread = Thread(target=lambda: drain_results.append(worker.drain_once()))
    drain_thread.start()
    assert executor_started.wait(timeout=5)

    cancelled = service.cancel("demo", job_id)
    assert cancelled.status == "running"
    assert cancelled.cancel_requested == 1

    release_executor.set()
    drain_thread.join(timeout=5)
    assert not drain_thread.is_alive()
    assert drain_results == [True]
    assert read_job(project_db, job_id).status == "cancelled"


def test_worker_atomic_claim_never_runs_after_queued_cancel_wins(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    project_db = data_root / "demo" / "story.db"
    job_id = insert_job_row(project_db, status="queued", job_type="analyze_document")
    competing = sqlite3.connect(project_db, timeout=0)
    competing.execute("PRAGMA busy_timeout = 0")
    cancel_won: list[bool] = []
    executed: list[int] = []
    original_open_database = job_worker_module.open_database

    def open_with_competing_cancel(config: DatabaseConfig) -> sqlite3.Connection:
        connection = original_open_database(config)

        def trace(statement: str) -> None:
            if "UPDATE style_jobs SET status = 'running'" not in statement:
                return
            try:
                competing.execute(
                    "UPDATE style_jobs SET status = 'cancelled', "
                    "finished_at = CURRENT_TIMESTAMP WHERE id = ? "
                    "AND status = 'queued'",
                    (job_id,),
                )
                competing.commit()
                cancel_won.append(True)
            except sqlite3.OperationalError:
                competing.rollback()
                cancel_won.append(False)

        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(job_worker_module, "open_database", open_with_competing_cancel)

    def executor(_connection: sqlite3.Connection, job: JobRecord) -> None:
        executed.append(job.id)

    worker = StyleAnalysisWorker(data_root=data_root, executor=executor)
    worker.notify("demo")
    try:
        assert worker.drain_once() is True
    finally:
        competing.close()

    assert cancel_won in ([True], [False])
    if cancel_won == [True]:
        assert executed == []
        assert read_job(project_db, job_id).status == "cancelled"


def test_worker_project_failure_isolation_keeps_thread_and_processes_other_project(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ProjectRegistry(data_root)
    registry.create("Project A", project_id="a")
    registry.create("Project B", project_id="b")
    a_db = data_root / "a" / "story.db"
    b_db = data_root / "b" / "story.db"
    insert_job_row(a_db, status="queued", job_type="analyze_document")
    b_job_id = insert_job_row(b_db, status="queued", job_type="analyze_document")
    processed = Event()
    observed: list[int] = []

    def executor(_connection: sqlite3.Connection, job: JobRecord) -> None:
        observed.append(job.id)
        processed.set()

    worker = StyleAnalysisWorker(data_root=data_root, executor=executor)
    original_process = worker._process_one
    original_remove = worker._remove_if_empty

    def fail_project_a(project_id: str) -> bool:
        if project_id == "a":
            raise RuntimeError("project A database unavailable")
        return original_process(project_id)

    def fail_cleanup_a(project_id: str) -> None:
        if project_id == "a":
            raise RuntimeError("project A cleanup unavailable")
        original_remove(project_id)

    monkeypatch.setattr(worker, "_process_one", fail_project_a)
    monkeypatch.setattr(worker, "_remove_if_empty", fail_cleanup_a)
    worker.start()
    try:
        worker.notify("a")
        worker.notify("b")
        assert processed.wait(timeout=5)
        assert worker.is_running
    finally:
        worker.stop()

    assert observed == [b_job_id]
    assert read_job(b_db, b_job_id).status == "succeeded"


def test_app_lifespan_owns_one_worker_instance(data_root: Path) -> None:
    app = create_app(ApiSettings(data_root=data_root))
    worker = app.state.style_analysis_worker
    assert worker.is_running is False

    with TestClient(app):
        assert app.state.style_analysis_worker is worker
        assert worker.is_running is True

    assert worker.is_running is False
