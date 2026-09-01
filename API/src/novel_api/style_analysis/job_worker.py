from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Lock, Thread, current_thread

from novel_core.config import DatabaseConfig
from novel_core.database import default_migration_dir, open_database
from novel_core.style_analysis.runtime_models import JobRecord

from novel_api.project_registry import ProjectRegistry
from novel_api.style_analysis.job_service import DatabaseConnection, StyleJobService

JobExecutor = Callable[[DatabaseConnection, JobRecord], None]


class StyleAnalysisWorker:
    def __init__(
        self,
        *,
        data_root: Path,
        executor: JobExecutor | None = None,
    ) -> None:
        self._registry = ProjectRegistry(data_root)
        self._executor = executor
        self._ready: deque[str] = deque()
        self._ready_set: set[str] = set()
        self._ready_lock = Lock()
        self._stop_event = Event()
        self._wake_event = Event()
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._recover_projects()
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name="novel-style-analysis-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=5)
        self._thread = None

    def notify(self, project_id: str) -> None:
        self._registry.resolve_path(project_id)
        self._enqueue_ready(project_id)
        self._wake_event.set()

    def drain_once(self) -> bool:
        project_id = self._pop_ready()
        if project_id is None:
            return False
        if self._executor is None:
            self._enqueue_ready(project_id, front=True)
            return False
        try:
            processed = self._process_one(project_id)
            if not processed:
                self._remove_if_empty(project_id)
        except Exception:
            return False
        return processed

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._executor is None:
                self._wake_event.wait(0.1)
                self._wake_event.clear()
                continue
            if not self.drain_once():
                self._wake_event.wait(0.1)
                self._wake_event.clear()

    def _recover_projects(self) -> None:
        for summary in self._registry.list():
            project_id = summary.project_id
            try:
                with self._open_project_connection(project_id) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        "UPDATE style_jobs SET status = 'failed', "
                        "finished_at = CURRENT_TIMESTAMP, "
                        "error_code = 'WORKER_INTERRUPTED', "
                        "error_message = 'worker interrupted before completion' "
                        "WHERE status = 'running'"
                    )
                    connection.execute(
                        "UPDATE style_analysis_runs SET status = 'failed', "
                        "finished_at = CURRENT_TIMESTAMP, "
                        "error_code = 'WORKER_INTERRUPTED', "
                        "error_message = 'worker interrupted before completion' "
                        "WHERE status = 'running'"
                    )
                    connection.commit()
                    queued = connection.execute(
                        "SELECT 1 FROM style_jobs WHERE status = 'queued' LIMIT 1"
                    ).fetchone()
                if queued is not None:
                    self._enqueue_ready(project_id)
            except Exception:
                continue

    def _process_one(self, project_id: str) -> bool:
        with self._open_project_connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id, job_type, payload_json, status, cancel_requested, "
                "progress_current, progress_total, result_json, warning_json, "
                "created_at, started_at, finished_at, error_code, error_message, "
                "version FROM style_jobs WHERE status = 'queued' "
                "ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            job = StyleJobService._record_from_row(row)
            claim = connection.execute(
                "UPDATE style_jobs SET status = 'running', "
                "started_at = COALESCE(started_at, CURRENT_TIMESTAMP) "
                "WHERE id = ? AND status = 'queued'",
                (job.id,),
            )
            if claim.rowcount != 1:
                connection.rollback()
                return False
            connection.commit()
            running_row = connection.execute(
                "SELECT id, job_type, payload_json, status, cancel_requested, "
                "progress_current, progress_total, result_json, warning_json, "
                "created_at, started_at, finished_at, error_code, error_message, "
                "version FROM style_jobs WHERE id = ?",
                (job.id,),
            ).fetchone()
            assert running_row is not None
            running = StyleJobService._record_from_row(running_row)
            try:
                assert self._executor is not None
                self._executor(connection, running)
                status_row = connection.execute(
                    "SELECT status, cancel_requested FROM style_jobs WHERE id = ?",
                    (job.id,),
                ).fetchone()
                assert status_row is not None
                current_status, cancel_requested = status_row
                if current_status == "running":
                    final_status = "cancelled" if cancel_requested else "succeeded"
                    connection.execute(
                        "UPDATE style_jobs SET status = ?, "
                        "finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (final_status, job.id),
                    )
            except Exception as exc:
                connection.execute(
                    "UPDATE style_jobs SET status = 'failed', "
                    "finished_at = CURRENT_TIMESTAMP, "
                    "error_code = 'WORKER_EXECUTION_FAILED', error_message = ? "
                    "WHERE id = ?",
                    (str(exc), job.id),
                )
            connection.commit()
            remaining = connection.execute(
                "SELECT 1 FROM style_jobs WHERE status = 'queued' LIMIT 1"
            ).fetchone()
        if remaining is not None:
            self._enqueue_ready(project_id)
        return True

    def _enqueue_ready(self, project_id: str, *, front: bool = False) -> None:
        with self._ready_lock:
            if project_id in self._ready_set:
                return
            if front:
                self._ready.appendleft(project_id)
            else:
                self._ready.append(project_id)
            self._ready_set.add(project_id)

    def _pop_ready(self) -> str | None:
        with self._ready_lock:
            if not self._ready:
                return None
            project_id = self._ready.popleft()
            self._ready_set.remove(project_id)
            return project_id

    def _remove_if_empty(self, project_id: str) -> None:
        with self._open_project_connection(project_id) as connection:
            queued = connection.execute(
                "SELECT 1 FROM style_jobs WHERE status = 'queued' LIMIT 1"
            ).fetchone()
        if queued is not None:
            self._enqueue_ready(project_id)

    @contextmanager
    def _open_project_connection(self, project_id: str) -> Iterator[DatabaseConnection]:
        project_dir = self._registry.resolve_path(project_id)
        connection = open_database(
            DatabaseConfig(
                db_path=project_dir / "story.db",
                migration_dir=default_migration_dir(),
            )
        )
        try:
            yield connection
        finally:
            connection.close()
