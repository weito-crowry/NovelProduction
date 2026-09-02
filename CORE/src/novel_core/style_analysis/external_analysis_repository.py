from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, cast

from novel_core.style_analysis.external_analysis_models import (
    ExternalAnalysisSessionRecord,
    ExternalAnalysisSessionRunRecord,
    ExternalAnalysisTaskRecord,
    ExternalSessionStatus,
    ExternalTaskStatus,
)
from novel_core.style_analysis.fingerprints import JsonValue, canonical_json_bytes
from novel_core.style_analysis.model_contracts import JsonObject
from novel_core.style_analysis.model_output_contracts import (
    ResponseContractRegistry,
    task_request_fingerprint,
)
from novel_core.style_analysis.resumable_models import PreparedModelCall

_SESSION_COLUMNS = (
    "id, document_id, reference_work_id, executor_provider, executor_model_id, "
    "runtime_contract_fingerprint, status, request_json, snapshot_json, cursor_json, "
    "result_json, warning_json, version, error_code, error_message, created_at, "
    "updated_at, finished_at"
)
_TASK_COLUMNS = (
    "id, session_id, analysis_run_id, sequence_no, call_key, analyzer_id, "
    "analyzer_version, prompt_id, prompt_version, response_contract_id, attempt_no, "
    "parent_task_id, request_fingerprint, request_json, response_json, "
    "response_fingerprint, status, error_json, version, created_at, updated_at, "
    "submitted_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _json(value: JsonValue) -> str:
    return canonical_json_bytes(value).decode("utf-8")


class ExternalAnalysisRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def insert_session(
        self,
        *,
        document_id: int | None,
        reference_work_id: int | None,
        executor_provider: str,
        executor_model_id: str,
        runtime_contract_fingerprint: str,
        request_json: JsonValue,
        snapshot_json: JsonValue,
        cursor_json: JsonValue,
    ) -> int:
        cursor = self.connection.execute(
            "INSERT INTO style_external_analysis_sessions "
            "(document_id, reference_work_id, executor_provider, executor_model_id, "
            "runtime_contract_fingerprint, status, request_json, snapshot_json, "
            "cursor_json) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            (
                document_id,
                reference_work_id,
                executor_provider,
                executor_model_id,
                runtime_contract_fingerprint,
                _json(request_json),
                _json(snapshot_json),
                _json(cursor_json),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("external session insert did not return an id")
        return int(cursor.lastrowid)

    def get_session(self, session_id: int) -> ExternalAnalysisSessionRecord | None:
        row = self.connection.execute(
            f"SELECT {_SESSION_COLUMNS} FROM style_external_analysis_sessions "
            "WHERE id = ?",
            (session_id,),
        ).fetchone()
        return None if row is None else ExternalAnalysisRepository._session(row)

    def list_sessions(
        self, *, status: ExternalSessionStatus | None = None, limit: int = 20
    ) -> tuple[ExternalAnalysisSessionRecord, ...]:
        query = f"SELECT {_SESSION_COLUMNS} FROM style_external_analysis_sessions"
        parameters: tuple[object, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        rows = self.connection.execute(query, (*parameters, limit)).fetchall()
        return tuple(self._session(row) for row in rows)

    def update_session(
        self,
        session_id: int,
        *,
        status: ExternalSessionStatus,
        cursor_json: JsonValue,
        result_json: JsonValue,
        warning_json: JsonValue,
        error_code: str | None = None,
        error_message: str | None = None,
        finished_at: str | None = None,
        increment_version: bool = True,
    ) -> None:
        self.connection.execute(
            "UPDATE style_external_analysis_sessions SET status = ?, cursor_json = ?, "
            "result_json = ?, warning_json = ?, error_code = ?, error_message = ?, "
            "finished_at = ?, updated_at = ?, version = version + ? WHERE id = ?",
            (
                status,
                _json(cursor_json),
                _json(result_json),
                _json(warning_json),
                error_code,
                error_message,
                finished_at,
                _now(),
                int(increment_version),
                session_id,
            ),
        )

    def insert_task(
        self,
        *,
        session_id: int,
        sequence_no: int,
        prepared_call: PreparedModelCall,
        attempt_no: int = 1,
        parent_task_id: int | None = None,
    ) -> int:
        if attempt_no not in {1, 2}:
            raise ValueError("EXTERNAL_TASK_ATTEMPT_INVALID")
        if (attempt_no == 1) != (parent_task_id is None):
            raise ValueError("EXTERNAL_TASK_PARENT_INVALID")
        owned_run = self.connection.execute(
            "SELECT 1 FROM style_external_analysis_session_runs "
            "WHERE session_id = ? AND run_id = ? AND run_role = 'created'",
            (session_id, prepared_call.analysis_run_id),
        ).fetchone()
        if owned_run is None:
            raise ValueError("EXTERNAL_TASK_RUN_NOT_OWNED")
        request = cast(
            JsonValue,
            {
                "call_key": prepared_call.call_key,
                "analysis_run_id": prepared_call.analysis_run_id,
                "analyzer_id": prepared_call.analyzer_id,
                "analyzer_version": prepared_call.analyzer_version,
                "prompt_id": prepared_call.prompt_id,
                "prompt_version": prepared_call.prompt_version,
                "response_contract_id": prepared_call.response_contract_id,
                "system_prompt": prepared_call.system_prompt,
                "user_payload": prepared_call.user_payload,
                "response_schema": prepared_call.response_schema,
            },
        )
        cursor = self.connection.execute(
            "INSERT INTO style_external_analysis_tasks "
            "(session_id, analysis_run_id, sequence_no, call_key, analyzer_id, "
            "analyzer_version, prompt_id, prompt_version, response_contract_id, "
            "attempt_no, parent_task_id, request_fingerprint, request_json, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (
                session_id,
                prepared_call.analysis_run_id,
                sequence_no,
                prepared_call.call_key,
                prepared_call.analyzer_id,
                prepared_call.analyzer_version,
                prepared_call.prompt_id,
                prepared_call.prompt_version,
                prepared_call.response_contract_id,
                attempt_no,
                parent_task_id,
                task_request_fingerprint(prepared_call, attempt_no=attempt_no),
                _json(request),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("external task insert did not return an id")
        return int(cursor.lastrowid)

    def get_task(self, task_id: int) -> ExternalAnalysisTaskRecord | None:
        row = self.connection.execute(
            f"SELECT {_TASK_COLUMNS} FROM style_external_analysis_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return None if row is None else self._task(row)

    def insert_repair_task(
        self,
        *,
        session_id: int,
        sequence_no: int,
        parent_task_id: int,
        original: PreparedModelCall,
        invalid_response: JsonObject,
        validation_errors: Sequence[str],
    ) -> int:
        parent = self.get_task(parent_task_id)
        if parent is None or parent.session_id != session_id or parent.attempt_no != 1:
            raise ValueError("EXTERNAL_TASK_PARENT_INVALID")
        repair = PreparedModelCall(
            call_key=original.call_key,
            analysis_run_id=original.analysis_run_id,
            analyzer_id=original.analyzer_id,
            analyzer_version=original.analyzer_version,
            prompt_id=original.prompt_id,
            prompt_version=original.prompt_version,
            response_contract_id=original.response_contract_id,
            system_prompt=ResponseContractRegistry.repair_system_prompt(),
            user_payload=cast(
                JsonObject,
                {
                    "original_request": original.user_payload,
                    "invalid_response": _json(cast(JsonValue, invalid_response)),
                    "validation_errors": list(validation_errors),
                },
            ),
            response_schema=original.response_schema,
        )
        repair_task_id = self.insert_task(
            session_id=session_id,
            sequence_no=sequence_no,
            prepared_call=repair,
            attempt_no=2,
            parent_task_id=parent_task_id,
        )
        self.connection.execute(
            "UPDATE style_external_analysis_tasks SET error_json = ? WHERE id = ?",
            (_json(cast(JsonValue, list(validation_errors))), repair_task_id),
        )
        return repair_task_id

    def current_pending_task(self, session_id: int) -> ExternalAnalysisTaskRecord:
        row = self.connection.execute(
            f"SELECT {_TASK_COLUMNS} FROM style_external_analysis_tasks "
            "WHERE session_id = ? AND status = 'pending'",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError("EXTERNAL_PENDING_TASK_NOT_FOUND")
        return self._task(row)

    def list_tasks(self, session_id: int) -> tuple[ExternalAnalysisTaskRecord, ...]:
        rows = self.connection.execute(
            f"SELECT {_TASK_COLUMNS} FROM style_external_analysis_tasks "
            "WHERE session_id = ? ORDER BY sequence_no",
            (session_id,),
        ).fetchall()
        return tuple(self._task(row) for row in rows)

    def finalize_task(
        self,
        *,
        task_id: int,
        expected_version: int,
        status: ExternalTaskStatus,
        response: JsonObject,
        error_codes: Sequence[str] = (),
    ) -> ExternalAnalysisTaskRecord:
        if status not in {"accepted", "repair_required", "rejected"}:
            raise ValueError("EXTERNAL_TASK_STATUS_INVALID")
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("NOT_FOUND")
        if task.version != expected_version:
            raise ValueError("VERSION_CONFLICT")
        if task.status != "pending":
            raise ValueError("EXTERNAL_TASK_ALREADY_FINALIZED")
        response_json = _json(cast(JsonValue, response))
        self.connection.execute(
            "UPDATE style_external_analysis_tasks SET response_json = ?, "
            "response_fingerprint = ?, status = ?, error_json = ?, "
            "version = version + 1, "
            "updated_at = ?, submitted_at = ? WHERE id = ?",
            (
                response_json,
                _fingerprint(response),
                status,
                _json(cast(JsonValue, list(error_codes))),
                _now(),
                _now(),
                task_id,
            ),
        )
        result = self.get_task(task_id)
        if result is None:
            raise RuntimeError("external task retrieval failed")
        return result

    def supersede_task(self, task_id: int, *, expected_version: int) -> None:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("NOT_FOUND")
        if task.version != expected_version:
            raise ValueError("VERSION_CONFLICT")
        if task.status != "pending":
            return
        self.connection.execute(
            "UPDATE style_external_analysis_tasks SET status = 'superseded', "
            "version = version + 1, updated_at = ? WHERE id = ?",
            (_now(), task_id),
        )

    def link_run(self, session_id: int, run_id: int, role: str) -> None:
        if role not in {"created", "reused"}:
            raise ValueError("EXTERNAL_RUN_ROLE_INVALID")
        self.connection.execute(
            "INSERT INTO style_external_analysis_session_runs "
            "(session_id, run_id, run_role) VALUES (?, ?, ?)",
            (session_id, run_id, role),
        )

    def linked_runs(
        self, session_id: int
    ) -> tuple[ExternalAnalysisSessionRunRecord, ...]:
        rows = self.connection.execute(
            "SELECT session_id, run_id, run_role "
            "FROM style_external_analysis_session_runs "
            "WHERE session_id = ? ORDER BY run_id",
            (session_id,),
        ).fetchall()
        return tuple(ExternalAnalysisSessionRunRecord(*row) for row in rows)

    def request_fingerprint(self, task_id: int) -> str:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("NOT_FOUND")
        value = json.loads(task.request_json)
        if not isinstance(value, dict):
            raise ValueError("EXTERNAL_TASK_REQUEST_INVALID")
        call = PreparedModelCall(
            call_key=str(value["call_key"]),
            analysis_run_id=int(value["analysis_run_id"]),
            analyzer_id=str(value["analyzer_id"]),
            analyzer_version=int(value["analyzer_version"]),
            prompt_id=str(value["prompt_id"]),
            prompt_version=int(value["prompt_version"]),
            response_contract_id=str(value["response_contract_id"]),
            system_prompt=str(value["system_prompt"]),
            user_payload=cast(JsonObject, value["user_payload"]),
            response_schema=cast(JsonObject, value["response_schema"]),
        )
        return task_request_fingerprint(call, attempt_no=task.attempt_no)

    def assert_session_invariants(self, session_id: int) -> None:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError("NOT_FOUND")
        count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM style_external_analysis_tasks "
                "WHERE session_id = ? AND status = 'pending'",
                (session_id,),
            ).fetchone()[0]
        )
        expected = 1 if session.status == "active" else 0
        if count != expected:
            raise ValueError("EXTERNAL_SESSION_PENDING_INVALID")

    @staticmethod
    def _session(row: Sequence[object]) -> ExternalAnalysisSessionRecord:
        return ExternalAnalysisSessionRecord(
            id=_as_int(row[0]),
            document_id=None if row[1] is None else _as_int(row[1]),
            reference_work_id=None if row[2] is None else _as_int(row[2]),
            executor_provider=str(row[3]),
            executor_model_id=str(row[4]),
            runtime_contract_fingerprint=str(row[5]),
            status=cast(ExternalSessionStatus, row[6]),
            request_json=str(row[7]),
            snapshot_json=str(row[8]),
            cursor_json=str(row[9]),
            result_json=str(row[10]),
            warning_json=str(row[11]),
            version=_as_int(row[12]),
            error_code=None if row[13] is None else str(row[13]),
            error_message=None if row[14] is None else str(row[14]),
            created_at=str(row[15]),
            updated_at=str(row[16]),
            finished_at=None if row[17] is None else str(row[17]),
        )

    @staticmethod
    def _task(row: Sequence[object]) -> ExternalAnalysisTaskRecord:
        return ExternalAnalysisTaskRecord(
            id=_as_int(row[0]),
            session_id=_as_int(row[1]),
            analysis_run_id=_as_int(row[2]),
            sequence_no=_as_int(row[3]),
            call_key=str(row[4]),
            analyzer_id=str(row[5]),
            analyzer_version=_as_int(row[6]),
            prompt_id=str(row[7]),
            prompt_version=_as_int(row[8]),
            response_contract_id=str(row[9]),
            attempt_no=_as_int(row[10]),
            parent_task_id=None if row[11] is None else _as_int(row[11]),
            request_fingerprint=str(row[12]),
            request_json=str(row[13]),
            response_json=None if row[14] is None else str(row[14]),
            response_fingerprint=None if row[15] is None else str(row[15]),
            status=cast(ExternalTaskStatus, row[16]),
            error_json=str(row[17]),
            version=_as_int(row[18]),
            created_at=str(row[19]),
            updated_at=str(row[20]),
            submitted_at=None if row[21] is None else str(row[21]),
        )


def _as_int(value: object) -> int:
    return int(cast(Any, value))


def _fingerprint(value: JsonObject) -> str:
    import hashlib

    return hashlib.sha256(canonical_json_bytes(cast(JsonValue, value))).hexdigest()
