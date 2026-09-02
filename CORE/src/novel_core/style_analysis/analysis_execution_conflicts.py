from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from novel_core.errors import AnalysisExecutionConflictError

_ACTIVE_JOB_STATUSES = ("queued", "running")


class AnalysisExecutionConflictChecker:
    """Canonical scope checker for internal and external analysis execution."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def assert_document_available(self, document_id: int) -> None:
        self.assert_targets_available(documents=(document_id,))

    def assert_reference_work_available(self, reference_work_id: int) -> None:
        self.assert_targets_available(reference_works=(reference_work_id,))

    def assert_targets_available(
        self,
        *,
        documents: Iterable[int] = (),
        reference_works: Iterable[int] = (),
        exclude_session_id: int | None = None,
    ) -> None:
        document_ids = {int(item) for item in documents}
        work_ids = {int(item) for item in reference_works}
        document_ids.update(self._work_document_ids(work_ids))
        work_ids.update(self._document_work_ids(document_ids))
        if not document_ids and not work_ids:
            return
        if self._active_jobs_overlap(document_ids, work_ids):
            raise AnalysisExecutionConflictError()
        if self._active_external_overlap(
            document_ids, work_ids, exclude_session_id=exclude_session_id
        ):
            raise AnalysisExecutionConflictError()

    def _active_jobs_overlap(self, document_ids: set[int], work_ids: set[int]) -> bool:
        rows = self.connection.execute(
            "SELECT job_type, payload_json FROM style_jobs WHERE status IN (?, ?)",
            _ACTIVE_JOB_STATUSES,
        ).fetchall()
        for job_type, payload_json in rows:
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if job_type == "analyze_document":
                value = payload.get("document_id")
                if isinstance(value, int) and value in document_ids:
                    return True
            elif job_type == "analyze_reference_work":
                value = payload.get("reference_work_id")
                if isinstance(value, int) and (
                    value in work_ids or value in self._document_work_ids(document_ids)
                ):
                    return True
        return False

    def _active_external_overlap(
        self,
        document_ids: set[int],
        work_ids: set[int],
        *,
        exclude_session_id: int | None,
    ) -> bool:
        query = (
            "SELECT id, document_id, reference_work_id "
            "FROM style_external_analysis_sessions WHERE status = 'active'"
        )
        parameters: tuple[object, ...] = ()
        if exclude_session_id is not None:
            query += " AND id <> ?"
            parameters = (exclude_session_id,)
        rows = self.connection.execute(query, parameters).fetchall()
        for _session_id, document_id, reference_work_id in rows:
            if document_id is not None and int(document_id) in document_ids:
                return True
            if reference_work_id is not None and int(reference_work_id) in work_ids:
                return True
        return False

    def _work_document_ids(self, work_ids: set[int]) -> set[int]:
        if not work_ids:
            return set()
        placeholders = ",".join("?" for _ in work_ids)
        rows = self.connection.execute(
            "SELECT sd.id FROM style_documents sd "
            "JOIN style_reference_episodes re "
            "ON re.id = sd.reference_episode_id "
            f"WHERE re.reference_work_id IN ({placeholders})",
            tuple(work_ids),
        ).fetchall()
        return {int(row[0]) for row in rows}

    def _document_work_ids(self, document_ids: set[int]) -> set[int]:
        if not document_ids:
            return set()
        placeholders = ",".join("?" for _ in document_ids)
        rows = self.connection.execute(
            "SELECT re.reference_work_id FROM style_documents sd "
            "JOIN style_reference_episodes re "
            "ON re.id = sd.reference_episode_id "
            f"WHERE sd.id IN ({placeholders})",
            tuple(document_ids),
        ).fetchall()
        return {int(row[0]) for row in rows}
