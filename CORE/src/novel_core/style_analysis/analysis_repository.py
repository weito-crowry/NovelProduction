from __future__ import annotations

import json
import sqlite3
from typing import cast

from novel_core.style_analysis.runtime_models import (
    AnalysisRunRecord,
    RunStatus,
)

_RUN_COLUMNS = (
    "id, document_id, analyzer_id, analyzer_version, text_revision_id, "
    "structure_revision_id, status, fingerprint, config_json, "
    "analysis_policy_version, policy_input_fingerprint, state_fingerprint, "
    "registry_input_fingerprint, model_provider, model_id, prompt_id, "
    "prompt_version, started_at, finished_at, error_code, error_message, "
    "warning_json, created_at"
)
_RUN_INSERT_COLUMNS = (
    "document_id, analyzer_id, analyzer_version, text_revision_id, "
    "structure_revision_id, status, fingerprint, config_json, "
    "analysis_policy_version, policy_input_fingerprint, state_fingerprint, "
    "registry_input_fingerprint, model_provider, model_id, prompt_id, "
    "prompt_version, started_at, finished_at, error_code, error_message, "
    "warning_json"
)


class AnalysisRunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def insert_run(
        self,
        *,
        document_id: int,
        analyzer_id: str,
        analyzer_version: int,
        text_revision_id: int,
        structure_revision_id: int,
        status: RunStatus,
        fingerprint: str,
        config_json: str,
        analysis_policy_version: int | None = None,
        policy_input_fingerprint: str | None = None,
        state_fingerprint: str | None = None,
        registry_input_fingerprint: str | None = None,
        model_provider: str | None = None,
        model_id: str | None = None,
        prompt_id: str | None = None,
        prompt_version: int | None = None,
        started_at: str,
        finished_at: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        warning_json: str = "[]",
    ) -> int:
        cursor = self._connection.execute(
            f"INSERT INTO style_analysis_runs ({_RUN_INSERT_COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ",
            (
                document_id,
                analyzer_id,
                analyzer_version,
                text_revision_id,
                structure_revision_id,
                status,
                fingerprint,
                config_json,
                analysis_policy_version,
                policy_input_fingerprint,
                state_fingerprint,
                registry_input_fingerprint,
                model_provider,
                model_id,
                prompt_id,
                prompt_version,
                started_at,
                finished_at,
                error_code,
                error_message,
                warning_json,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("analysis run insert did not return an id")
        return cursor.lastrowid

    def add_dependency(self, run_id: int, dependency_run_id: int) -> None:
        self._connection.execute(
            "INSERT INTO style_analysis_run_dependencies "
            "(run_id, dependency_run_id) VALUES (?, ?)",
            (run_id, dependency_run_id),
        )

    def add_structure_analysis_source(
        self, structure_revision_id: int, boundary_analysis_run_id: int
    ) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO style_structure_analysis_sources "
            "(structure_revision_id, boundary_analysis_run_id) VALUES (?, ?)",
            (structure_revision_id, boundary_analysis_run_id),
        )

    def finish_run(
        self,
        run_id: int,
        *,
        status: RunStatus,
        finished_at: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        warning_json: str = "[]",
    ) -> None:
        if status == "running":
            raise ValueError("RUN_STATUS_INVALID")
        try:
            json.loads(warning_json)
        except json.JSONDecodeError as exc:
            raise ValueError("WARNING_JSON_INVALID") from exc
        self._connection.execute(
            "UPDATE style_analysis_runs SET status = ?, "
            "finished_at = COALESCE(?, CURRENT_TIMESTAMP), error_code = ?, "
            "error_message = ?, warning_json = ? WHERE id = ?",
            (status, finished_at, error_code, error_message, warning_json, run_id),
        )

    def get_run(self, run_id: int) -> AnalysisRunRecord | None:
        row = self._connection.execute(
            f"SELECT {_RUN_COLUMNS} FROM style_analysis_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return None if row is None else self._record_from_row(row)

    def succeeded_runs(
        self,
        *,
        document_id: int,
        analyzer_id: str,
        analyzer_version: int,
        text_revision_id: int,
        structure_revision_id: int,
    ) -> tuple[AnalysisRunRecord, ...]:
        return self.runs(
            document_id=document_id,
            analyzer_id=analyzer_id,
            analyzer_version=analyzer_version,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            statuses=("succeeded",),
        )

    def runs(
        self,
        *,
        document_id: int,
        analyzer_id: str,
        analyzer_version: int,
        text_revision_id: int,
        structure_revision_id: int,
        statuses: tuple[RunStatus, ...],
    ) -> tuple[AnalysisRunRecord, ...]:
        if not statuses:
            return ()
        placeholders = ", ".join("?" for _ in statuses)
        rows = self._connection.execute(
            f"SELECT {_RUN_COLUMNS} FROM style_analysis_runs "
            "WHERE document_id = ? AND analyzer_id = ? "
            "AND analyzer_version = ? AND text_revision_id = ? "
            f"AND structure_revision_id = ? AND status IN ({placeholders}) "
            "ORDER BY created_at DESC, id DESC",
            (
                document_id,
                analyzer_id,
                analyzer_version,
                text_revision_id,
                structure_revision_id,
                *statuses,
            ),
        ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def _record_from_row(
        self, row: sqlite3.Row | tuple[object, ...]
    ) -> AnalysisRunRecord:
        dependencies = self._connection.execute(
            "SELECT dep.analyzer_id, links.dependency_run_id "
            "FROM style_analysis_run_dependencies AS links "
            "JOIN style_analysis_runs AS dep "
            "ON dep.id = links.dependency_run_id "
            "WHERE links.run_id = ? "
            "ORDER BY dep.analyzer_id, links.dependency_run_id",
            (row[0],),
        ).fetchall()
        return AnalysisRunRecord(
            id=cast(int, row[0]),
            document_id=cast(int, row[1]),
            analyzer_id=cast(str, row[2]),
            analyzer_version=cast(int, row[3]),
            text_revision_id=cast(int, row[4]),
            structure_revision_id=cast(int, row[5]),
            status=cast(RunStatus, row[6]),
            fingerprint=cast(str, row[7]),
            config_json=cast(str, row[8]),
            analysis_policy_version=cast(int | None, row[9]),
            policy_input_fingerprint=cast(str | None, row[10]),
            state_fingerprint=cast(str | None, row[11]),
            registry_input_fingerprint=cast(str | None, row[12]),
            model_provider=cast(str | None, row[13]),
            model_id=cast(str | None, row[14]),
            prompt_id=cast(str | None, row[15]),
            prompt_version=cast(int | None, row[16]),
            started_at=cast(str, row[17]),
            finished_at=cast(str | None, row[18]),
            error_code=cast(str | None, row[19]),
            error_message=cast(str | None, row[20]),
            warning_json=cast(str, row[21]),
            created_at=cast(str, row[22]),
            dependency_runs=tuple(dependencies),
        )
