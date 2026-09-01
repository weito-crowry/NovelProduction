from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast

from novel_core.config import DatabaseConfig
from novel_core.database import default_migration_dir, open_database
from novel_core.style_analysis.fingerprints import JsonObject
from novel_core.style_analysis.runtime_models import JobRecord, JobStatus, JobType

from novel_api.project_registry import ProjectRegistry

_JOB_COLUMNS = (
    "id, job_type, payload_json, status, cancel_requested, progress_current, "
    "progress_total, result_json, warning_json, created_at, started_at, "
    "finished_at, error_code, error_message, version"
)
_JOB_TYPES = frozenset(
    (
        "analyze_document",
        "analyze_reference_work",
        "recompute_aggregate",
        "run_lint",
    )
)
_ANALYSIS_JOB_TYPES = frozenset(("analyze_document", "analyze_reference_work"))
_TERMINAL_STATUSES = frozenset(("succeeded", "partial", "failed", "cancelled"))


class DatabaseCursor(Protocol):
    @property
    def lastrowid(self) -> int | None: ...

    def fetchone(self) -> Sequence[object] | None: ...


class DatabaseConnection(Protocol):
    def execute(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> DatabaseCursor: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...


class StyleJobService:
    def __init__(
        self,
        *,
        data_root: Path,
        notify: Callable[[str], None] | None = None,
    ) -> None:
        self._registry = ProjectRegistry(data_root)
        self._notify = notify

    def enqueue(
        self, project_id: str, job_type: JobType, payload: JsonObject
    ) -> JobRecord:
        self._validate_job_type(job_type)
        if not isinstance(payload, dict):
            raise ValueError("JOB_PAYLOAD_INVALID")
        try:
            payload_json = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("JOB_PAYLOAD_INVALID") from exc

        with self._open_connection(project_id) as connection:
            cursor = connection.execute(
                "INSERT INTO style_jobs (job_type, payload_json, status) "
                "VALUES (?, ?, 'queued')",
                (job_type, payload_json),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("job insert did not return an id")
            connection.commit()
            job = self._get_from_connection(connection, cursor.lastrowid)
            if job is None:
                raise RuntimeError("job retrieval failed")

        if self._notify is not None:
            self._notify(project_id)
        return job

    def get(self, project_id: str, job_id: int) -> JobRecord | None:
        with self._open_connection(project_id) as connection:
            return self._get_from_connection(connection, job_id)

    def cancel(self, project_id: str, job_id: int) -> JobRecord:
        with self._open_connection(project_id) as connection:
            job = self._require_from_connection(connection, job_id)
            if job.status == "queued":
                connection.execute(
                    "UPDATE style_jobs SET status = 'cancelled', "
                    "finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (job_id,),
                )
            elif job.status == "running":
                connection.execute(
                    "UPDATE style_jobs SET cancel_requested = 1 WHERE id = ?",
                    (job_id,),
                )
            connection.commit()
            return self._require_from_connection(connection, job_id)

    def retry(self, project_id: str, job_id: int) -> JobRecord:
        with self._open_connection(project_id) as connection:
            original = self._require_from_connection(connection, job_id)
            if original.status not in _TERMINAL_STATUSES:
                raise ValueError("JOB_NOT_TERMINAL")
            try:
                payload = json.loads(original.payload_json)
            except json.JSONDecodeError as exc:
                raise ValueError("JOB_PAYLOAD_INVALID") from exc
            if not isinstance(payload, dict):
                raise ValueError("JOB_PAYLOAD_INVALID")
            payload["retry_of_job_id"] = original.id
            payload_json = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            cursor = connection.execute(
                "INSERT INTO style_jobs (job_type, payload_json, status) "
                "VALUES (?, ?, 'queued')",
                (original.job_type, payload_json),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("retry job insert did not return an id")
            connection.commit()
            retried = self._get_from_connection(connection, cursor.lastrowid)
            if retried is None:
                raise RuntimeError("retry job retrieval failed")
            return retried

    def set_status(self, project_id: str, job_id: int, status: JobStatus) -> JobRecord:
        if status not in {
            "queued",
            "running",
            "succeeded",
            "partial",
            "failed",
            "cancelled",
        }:
            raise ValueError("JOB_STATUS_INVALID")
        with self._open_connection(project_id) as connection:
            job = self._require_from_connection(connection, job_id)
            if status == "partial" and job.job_type not in _ANALYSIS_JOB_TYPES:
                raise ValueError("PARTIAL_STATUS_NOT_ALLOWED")
            if job.status in _TERMINAL_STATUSES and status != job.status:
                raise ValueError("JOB_TERMINAL")
            if status == "running":
                connection.execute(
                    "UPDATE style_jobs SET status = 'running', "
                    "started_at = COALESCE(started_at, CURRENT_TIMESTAMP) "
                    "WHERE id = ?",
                    (job_id,),
                )
            elif status in _TERMINAL_STATUSES:
                connection.execute(
                    "UPDATE style_jobs SET status = ?, "
                    "finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP) "
                    "WHERE id = ?",
                    (status, job_id),
                )
            else:
                connection.execute(
                    "UPDATE style_jobs SET status = ? WHERE id = ?",
                    (status, job_id),
                )
            connection.commit()
            return self._require_from_connection(connection, job_id)

    @contextmanager
    def _open_connection(self, project_id: str) -> Iterator[DatabaseConnection]:
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

    @classmethod
    def _validate_job_type(cls, job_type: str) -> None:
        if job_type not in _JOB_TYPES:
            raise ValueError("JOB_TYPE_INVALID")

    @staticmethod
    def _get_from_connection(
        connection: DatabaseConnection, job_id: int
    ) -> JobRecord | None:
        row = connection.execute(
            f"SELECT {_JOB_COLUMNS} FROM style_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return None if row is None else StyleJobService._record_from_row(row)

    @staticmethod
    def _require_from_connection(
        connection: DatabaseConnection, job_id: int
    ) -> JobRecord:
        job = StyleJobService._get_from_connection(connection, job_id)
        if job is None:
            raise ValueError("JOB_NOT_FOUND")
        return job

    @staticmethod
    def _record_from_row(row: Sequence[object]) -> JobRecord:
        return JobRecord(
            id=cast(int, row[0]),
            job_type=cast(JobType, row[1]),
            payload_json=cast(str, row[2]),
            status=cast(JobStatus, row[3]),
            cancel_requested=cast(int, row[4]),
            progress_current=cast(int | None, row[5]),
            progress_total=cast(int | None, row[6]),
            result_json=cast(str, row[7]),
            warning_json=cast(str, row[8]),
            created_at=cast(str, row[9]),
            started_at=cast(str | None, row[10]),
            finished_at=cast(str | None, row[11]),
            error_code=cast(str | None, row[12]),
            error_message=cast(str | None, row[13]),
            version=cast(int, row[14]),
        )
