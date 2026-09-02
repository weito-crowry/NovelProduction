from __future__ import annotations

import json
from typing import Any, cast

from novel_core.errors import (
    ExternalAnalysisSessionNotFoundError,
    ExternalAnalysisTaskNotFoundError,
)
from novel_core.style_analysis.external_analysis_models import (
    ExternalAnalysisSessionRecord,
    ExternalAnalysisTaskRecord,
)
from novel_core.style_analysis.fingerprints import JsonValue
from novel_core.style_analysis.model_contracts import JsonObject

from novel_api.style_analysis.external_service_operations import (
    ExternalAnalysisServiceHost,
)


class ExternalAnalysisViewsMixin(ExternalAnalysisServiceHost):
    def _session(self, session_id: int) -> ExternalAnalysisSessionRecord:
        session = self.repository.get_session(session_id)
        if session is None:
            raise ExternalAnalysisSessionNotFoundError()
        return session

    def _task(self, task_id: int) -> ExternalAnalysisTaskRecord:
        task = self.repository.get_task(task_id)
        if task is None:
            raise ExternalAnalysisTaskNotFoundError()
        return task

    def _request(self, session: ExternalAnalysisSessionRecord) -> JsonObject:
        return _object(session.request_json)

    def _cursor(self, session: ExternalAnalysisSessionRecord) -> JsonObject:
        return _object(session.cursor_json)

    def _result(self, session: ExternalAnalysisSessionRecord) -> JsonObject:
        return _object(session.result_json)

    def _warnings(self, session: ExternalAnalysisSessionRecord) -> list[object]:
        value = json.loads(session.warning_json)
        return value if isinstance(value, list) else []

    def _bump_session(
        self, session: ExternalAnalysisSessionRecord, cursor: JsonObject
    ) -> None:
        self.repository.update_session(
            session.id,
            status="active",
            cursor_json=cast(JsonValue, cursor),
            result_json=cast(JsonValue, self._result(session)),
            warning_json=cast(JsonValue, self._warnings(session)),
        )

    def _next_sequence(self, session_id: int) -> int:
        rows = self.repository.list_tasks(session_id)
        return max((item.sequence_no for item in rows), default=0) + 1

    def _progress(self, session: ExternalAnalysisSessionRecord) -> dict[str, object]:
        cursor = self._cursor(session)
        tasks = self.repository.list_tasks(session.id)
        documents = cast(list[dict[str, object]], cursor.get("documents", []))
        index = int(cast(Any, cursor.get("document_index", 0)))
        engine_cursor = cast(JsonObject, cursor.get("engine_cursor", {}))
        return {
            "documents_completed": index,
            "documents_total": len(documents),
            "current_document_id": (
                documents[index].get("document_id") if index < len(documents) else None
            ),
            "stage": engine_cursor.get("stage"),
            "stage_index": engine_cursor.get("stage_index"),
            "stage_total": engine_cursor.get("stage_total", 15),
            "model_tasks_completed": sum(
                item.response_json is not None for item in tasks
            ),
        }

    def _task_response(
        self, session: ExternalAnalysisSessionRecord
    ) -> dict[str, object] | None:
        if session.status != "active":
            return None
        task = self.repository.current_pending_task(session.id)
        request = _object(task.request_json)
        return {
            "task_id": task.id,
            "task_version": task.version,
            "session_id": task.session_id,
            "analysis_run_id": task.analysis_run_id,
            "call_key": task.call_key,
            "analyzer_id": task.analyzer_id,
            "analyzer_version": task.analyzer_version,
            "prompt_id": task.prompt_id,
            "prompt_version": task.prompt_version,
            "response_contract_id": task.response_contract_id,
            "system_prompt": request.get("system_prompt"),
            "user_payload": request.get("user_payload"),
            "response_schema": request.get("response_schema"),
            "attempt_no": task.attempt_no,
            "max_attempts": 2,
            "validation_errors": _list(task.error_json),
        }

    def _summary(self, session: ExternalAnalysisSessionRecord) -> dict[str, object]:
        target = self._request(session).get("target", {})
        return {
            "session_id": session.id,
            "version": session.version,
            "target": target,
            "status": session.status,
            "executor_provider": session.executor_provider,
            "executor_model_id": session.executor_model_id,
            "progress": self._progress(session),
            "error_code": session.error_code,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "finished_at": session.finished_at,
        }


def _object(value: str) -> JsonObject:
    import json

    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("EXTERNAL_JSON_OBJECT_REQUIRED")
    return cast(JsonObject, parsed)


def _list(value: str) -> list[object]:
    import json

    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []
