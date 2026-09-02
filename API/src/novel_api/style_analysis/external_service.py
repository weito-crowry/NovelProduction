from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping
from typing import Any, cast

from novel_core.errors import (
    ExternalAnalysisSessionNotFoundError,
    ExternalAnalysisTaskNotFoundError,
    ExternalExecutorMismatchError,
    ExternalSessionTerminalError,
    ExternalTaskAlreadyFinalizedError,
    ExternalTaskNotCurrentError,
    VersionConflictError,
)
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.external_analysis_repository import (
    ExternalAnalysisRepository,
)
from novel_core.style_analysis.external_analysis_runtime import (
    analysis_policy_json,
    current_analysis_input_fingerprints,
    external_analysis_runtime_contract_fingerprint,
)
from novel_core.style_analysis.fingerprints import JsonValue
from novel_core.style_analysis.model_contracts import JsonObject
from novel_core.style_analysis.resumable_models import (
    CompletedModelCall,
)
from novel_core.style_analysis.runtime_models import AnalysisPolicy

from novel_api.style_analysis.external_service_operations import (
    ExternalAnalysisOperationsMixin,
    _now,
    _policy,
    _prepared,
    _response_fingerprint,
)
from novel_api.style_analysis.external_service_views import ExternalAnalysisViewsMixin
from novel_api.style_analysis.job_service import DatabaseConnection

CAPTURE_PROJECT_DRAFT = Callable[..., dict[str, object]]
_PROVIDER = "chatgpt_mcp"
_TERMINAL = frozenset({"succeeded", "partial", "failed", "cancelled"})


class ExternalAnalysisService(
    ExternalAnalysisOperationsMixin, ExternalAnalysisViewsMixin
):
    def __init__(
        self,
        connection: DatabaseConnection,
        *,
        capture_project_draft: CAPTURE_PROJECT_DRAFT | None = None,
    ) -> None:
        self.connection = connection
        self.repository = ExternalAnalysisRepository(cast(Any, connection))
        self.capture_project_draft = capture_project_draft

    def start(
        self,
        *,
        target: Mapping[str, object],
        executor_model_id: str,
        rebuild_structure: bool = False,
    ) -> dict[str, object]:
        if not executor_model_id.strip():
            raise ValueError("EXTERNAL_EXECUTOR_MODEL_REQUIRED")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            snapshot, documents, document_id, reference_work_id = self._preflight(
                target, rebuild_structure
            )
            policy = AnalysisPolicy()
            request = {
                "schema_version": 1,
                "target": dict(target),
                "executor_model_id": executor_model_id,
                "rebuild_structure": rebuild_structure,
                "analysis_policy": analysis_policy_json(policy),
            }
            session_id = self.repository.insert_session(
                document_id=document_id,
                reference_work_id=reference_work_id,
                executor_provider=_PROVIDER,
                executor_model_id=executor_model_id,
                runtime_contract_fingerprint=(
                    external_analysis_runtime_contract_fingerprint()
                ),
                request_json=cast(JsonValue, request),
                snapshot_json=cast(JsonValue, snapshot),
                cursor_json=cast(
                    JsonValue,
                    self._initial_cursor(documents),
                ),
            )
            cursor, result, pending = self._advance_session(
                session_id=session_id,
                session_cursor=self._initial_cursor(documents),
                documents=documents,
                policy=policy,
                completed_call=None,
            )
            self._save_advance(
                session_id=session_id,
                cursor=cursor,
                result=result,
                pending=pending,
                increment_version=False,
            )
            self.repository.assert_session_invariants(session_id)
            self.connection.commit()
            return self.snapshot(session_id)
        except Exception:
            self.connection.rollback()
            raise

    def get(self, session_id: int) -> dict[str, object]:
        if self.repository.get_session(session_id) is None:
            raise ExternalAnalysisSessionNotFoundError()
        return self.snapshot(session_id)

    def list(
        self, *, status: str | None = None, limit: int = 20
    ) -> builtins.list[dict[str, object]]:
        records = self.repository.list_sessions(status=cast(Any, status), limit=limit)
        return [self._summary(record) for record in records]

    def submit(
        self,
        *,
        session_id: int,
        task_id: int,
        expected_task_version: int,
        executor_model_id: str,
        response: JsonObject,
    ) -> dict[str, object]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            session = self._session(session_id)
            task = self._task(task_id)
            if task.session_id != session.id:
                raise ExternalAnalysisTaskNotFoundError()
            response_fingerprint = _response_fingerprint(response)
            if task.status != "pending":
                if task.response_fingerprint == response_fingerprint:
                    self.connection.rollback()
                    return self.snapshot(session_id)
                if task.status != "superseded":
                    raise ExternalTaskAlreadyFinalizedError()
            if session.status != "active":
                raise ExternalSessionTerminalError()
            if session.executor_model_id != executor_model_id:
                raise ExternalExecutorMismatchError()
            current = self.repository.current_pending_task(session_id)
            if current.id != task.id:
                raise ExternalTaskNotCurrentError()
            if task.version != expected_task_version:
                raise VersionConflictError()
            if (
                session.runtime_contract_fingerprint
                != external_analysis_runtime_contract_fingerprint()
            ):
                self._reject_for_drift(
                    session, task, response, "EXTERNAL_ANALYSIS_CONTRACT_CHANGED"
                )
                self.connection.commit()
                return self.snapshot(session_id)
            policy = _policy(self._request(session).get("analysis_policy"))
            run = AnalysisRunRepository(cast(Any, self.connection)).get_run(
                task.analysis_run_id
            )
            if run is not None:
                state_fingerprint, policy_fingerprint = (
                    current_analysis_input_fingerprints(
                        cast(Any, self.connection), policy, run.id
                    )
                )
                if (
                    run.state_fingerprint != state_fingerprint
                    or run.policy_input_fingerprint != policy_fingerprint
                ):
                    self._reject_for_drift(
                        session, task, response, "EXTERNAL_ANALYSIS_INPUT_CHANGED"
                    )
                    self.connection.commit()
                    return self.snapshot(session_id)
            prepared = _prepared(task)
            validation_errors = self._repairable_errors(prepared, response)
            if validation_errors:
                if task.attempt_no == 2:
                    finalized = self.repository.finalize_task(
                        task_id=task.id,
                        expected_version=task.version,
                        status="rejected",
                        response=response,
                        error_codes=validation_errors,
                    )
                    completed = CompletedModelCall(
                        call_key=task.call_key,
                        error_code="MODEL_CONTRACT_INVALID",
                        error_message=";".join(validation_errors),
                    )
                    self._resume_after_submit(session, finalized, completed)
                else:
                    self.repository.finalize_task(
                        task_id=task.id,
                        expected_version=task.version,
                        status="repair_required",
                        response=response,
                        error_codes=validation_errors,
                    )
                    self.repository.insert_repair_task(
                        session_id=session.id,
                        sequence_no=self._next_sequence(session.id),
                        parent_task_id=task.id,
                        original=prepared,
                        invalid_response=response,
                        validation_errors=validation_errors,
                    )
                    self._bump_session(session, self._cursor(session))
                self.repository.assert_session_invariants(session.id)
                self.connection.commit()
                return self.snapshot(session.id)
            finalized = self.repository.finalize_task(
                task_id=task.id,
                expected_version=task.version,
                status="accepted",
                response=response,
            )
            self._resume_after_submit(
                session,
                finalized,
                CompletedModelCall(call_key=task.call_key, response=response),
            )
            self.repository.assert_session_invariants(session.id)
            self.connection.commit()
            return self.snapshot(session.id)
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def cancel(
        self, *, session_id: int, expected_session_version: int
    ) -> dict[str, object]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            session = self._session(session_id)
            if session.status != "active":
                raise ExternalSessionTerminalError()
            if session.version != expected_session_version:
                raise VersionConflictError()
            pending = self.repository.current_pending_task(session.id)
            self.repository.supersede_task(pending.id, expected_version=pending.version)
            run_repository = AnalysisRunRepository(cast(Any, self.connection))
            for link in self.repository.linked_runs(session.id):
                run = run_repository.get_run(link.run_id)
                if (
                    link.run_role == "created"
                    and run is not None
                    and run.status == "running"
                ):
                    run_repository.finish_run(
                        run.id, status="cancelled", error_code="ANALYSIS_CANCELLED"
                    )
            self.repository.update_session(
                session.id,
                status="cancelled",
                cursor_json=cast(JsonValue, self._cursor(session)),
                result_json=cast(JsonValue, self._result(session)),
                warning_json=cast(JsonValue, self._warnings(session)),
                finished_at=_now(),
            )
            self.connection.commit()
            return self.snapshot(session.id)
        except Exception:
            self.connection.rollback()
            raise

    def snapshot(self, session_id: int) -> dict[str, object]:
        session = self._session(session_id)
        return {
            "session_id": session.id,
            "version": session.version,
            "status": session.status,
            "executor_provider": session.executor_provider,
            "executor_model_id": session.executor_model_id,
            "progress": self._progress(session),
            "warnings": self._warnings(session),
            "result": self._result(session),
            "error_code": session.error_code,
            "error_message": session.error_message,
            "task": self._task_response(session),
        }

    @staticmethod
    def _initial_cursor(
        documents: builtins.list[dict[str, int | None]],
    ) -> JsonObject:
        return {
            "schema_version": 1,
            "document_index": 0,
            "documents": cast(JsonValue, documents),
            "engine_cursor": {"schema_version": 1},
        }

    @staticmethod
    def _safe_cursor(cursor: JsonObject) -> JsonObject:
        value = dict(cursor)
        value.pop("current_payload", None)
        value.pop("stage_responses", None)
        return value
