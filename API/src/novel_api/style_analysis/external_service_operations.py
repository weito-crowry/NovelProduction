from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, cast

from novel_core.style_analysis.analysis_execution_conflicts import (
    AnalysisExecutionConflictChecker,
)
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.external_analysis_models import (
    ExternalAnalysisSessionRecord,
    ExternalAnalysisTaskRecord,
)
from novel_core.style_analysis.external_analysis_repository import (
    ExternalAnalysisRepository,
)
from novel_core.style_analysis.fingerprints import JsonValue, canonical_json_bytes
from novel_core.style_analysis.model_contracts import JsonObject
from novel_core.style_analysis.model_output_contracts import ResponseContractRegistry
from novel_core.style_analysis.resumable_engine import ResumableDocumentAnalysisEngine
from novel_core.style_analysis.resumable_models import (
    CompletedModelCall,
    DocumentAnalysisRequest,
    PreparedModelCall,
)
from novel_core.style_analysis.runtime_models import AnalysisPolicy

_PROVIDER = "chatgpt_mcp"


class ExternalAnalysisServiceHost:
    connection: Any
    repository: ExternalAnalysisRepository
    capture_project_draft: Callable[..., dict[str, object]] | None

    def _cursor(self, session: ExternalAnalysisSessionRecord) -> JsonObject:
        raise NotImplementedError

    def _request(self, session: ExternalAnalysisSessionRecord) -> JsonObject:
        raise NotImplementedError

    def _safe_cursor(self, cursor: JsonObject) -> JsonObject:
        raise NotImplementedError

    def _session(self, session_id: int) -> ExternalAnalysisSessionRecord:
        raise NotImplementedError

    def _task(self, task_id: int) -> ExternalAnalysisTaskRecord:
        raise NotImplementedError

    def _result(self, session: ExternalAnalysisSessionRecord) -> JsonObject:
        raise NotImplementedError

    def _warnings(self, session: ExternalAnalysisSessionRecord) -> list[object]:
        raise NotImplementedError

    def _next_sequence(self, session_id: int) -> int:
        raise NotImplementedError


class ExternalAnalysisOperationsMixin(ExternalAnalysisServiceHost):
    def _preflight(
        self, target: Mapping[str, object], rebuild_structure: bool
    ) -> tuple[JsonObject, list[dict[str, int | None]], int | None, int | None]:
        kind = target.get("kind")
        if kind == "document":
            document_id = _positive(target.get("document_id"), "DOCUMENT_ID_REQUIRED")
            text_id = _positive(
                target.get("text_revision_id"), "TEXT_REVISION_REQUIRED"
            )
            structure_id = _optional_positive(target.get("structure_revision_id"))
            if structure_id is not None and rebuild_structure:
                raise ValueError("STRUCTURE_REBUILD_CONFLICT")
            row = self.connection.execute(
                "SELECT current_text_revision_id, current_structure_revision_id "
                "FROM style_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if row is None:
                raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
            text_row = self.connection.execute(
                "SELECT id FROM style_text_revisions WHERE id = ? AND document_id = ?",
                (text_id, document_id),
            ).fetchone()
            if text_row is None:
                raise ValueError("TEXT_REVISION_DOCUMENT_MISMATCH")
            if structure_id is not None:
                structure_row = self.connection.execute(
                    "SELECT text_revision_id FROM style_structure_revisions "
                    "WHERE id = ?",
                    (structure_id,),
                ).fetchone()
                if structure_row is None or int(structure_row[0]) != text_id:
                    raise ValueError("STRUCTURE_TEXT_REVISION_MISMATCH")
            AnalysisExecutionConflictChecker(
                cast(Any, self.connection)
            ).assert_document_available(document_id)
            current_text = row[0]
            current_structure = row[1]
            snapshot = {
                "schema_version": 1,
                "target_kind": "document",
                "document_id": document_id,
                "text_revision_id": text_id,
                "requested_structure_revision_id": structure_id,
                "initial_current_text_revision_id": current_text,
                "initial_current_structure_revision_id": current_structure,
                "target_was_current_text": current_text == text_id,
            }
            return (
                snapshot,
                [
                    {
                        "document_id": document_id,
                        "text_revision_id": text_id,
                        "structure_revision_id": structure_id,
                    }
                ],
                document_id,
                None,
            )
        if kind == "project_episode":
            episode_id = _positive(target.get("episode_id"), "EPISODE_ID_REQUIRED")
            draft_id = _positive(target.get("draft_id"), "DRAFT_ID_REQUIRED")
            if self.capture_project_draft is None:
                raise ValueError("PROJECT_DRAFT_CAPTURE_UNAVAILABLE")
            captured = self.capture_project_draft(
                episode_id=episode_id, draft_id=draft_id
            )
            (
                snapshot,
                document_items,
                captured_document_id,
                captured_reference_work_id,
            ) = self._preflight(
                {
                    "kind": "document",
                    "document_id": captured["document_id"],
                    "text_revision_id": captured["captured_text_revision_id"],
                },
                rebuild_structure,
            )
            snapshot.update(
                {
                    "target_kind": "project_episode",
                    "episode_id": episode_id,
                    "draft_id": draft_id,
                }
            )
            if captured_document_id is None:
                raise ValueError("PROJECT_DRAFT_DOCUMENT_REQUIRED")
            return (
                snapshot,
                document_items,
                captured_document_id,
                captured_reference_work_id,
            )
        if kind == "reference_work":
            work_id = _positive(
                target.get("reference_work_id"), "REFERENCE_WORK_ID_REQUIRED"
            )
            AnalysisExecutionConflictChecker(
                cast(Any, self.connection)
            ).assert_reference_work_available(work_id)
            rows = self.connection.execute(
                "SELECT re.id, re.order_index, sd.id, sd.current_text_revision_id, "
                "sd.current_structure_revision_id "
                "FROM style_reference_episodes re "
                "JOIN style_documents sd ON sd.reference_episode_id = re.id "
                "WHERE re.reference_work_id = ? ORDER BY re.order_index, re.id",
                (work_id,),
            ).fetchall()
            if not rows:
                raise ValueError("REFERENCE_WORK_NOT_FOUND")
            documents: list[dict[str, int | None]] = []
            episodes: list[JsonObject] = []
            for episode_id, order_index, document_id, text_id, structure_id in rows:
                if text_id is None:
                    raise ValueError("TEXT_REVISION_REQUIRED")
                documents.append(
                    {
                        "document_id": int(document_id),
                        "text_revision_id": int(text_id),
                        "structure_revision_id": None,
                    }
                )
                episodes.append(
                    {
                        "reference_episode_id": int(episode_id),
                        "order_index": int(order_index),
                        "document_id": int(document_id),
                        "snapshot_text_revision_id": int(text_id),
                        "initial_current_structure_revision_id": structure_id,
                    }
                )
            return (
                {
                    "schema_version": 1,
                    "target_kind": "reference_work",
                    "reference_work_id": work_id,
                    "episodes": episodes,
                },
                documents,
                None,
                work_id,
            )
        raise ValueError("EXTERNAL_TARGET_INVALID")

    def _advance_session(
        self,
        *,
        session_id: int,
        session_cursor: JsonObject,
        documents: list[dict[str, int | None]],
        policy: AnalysisPolicy,
        completed_call: CompletedModelCall | None,
        exclude_call_key: str | None = None,
    ) -> tuple[JsonObject, Any | None, PreparedModelCall | None]:
        index = int(cast(Any, session_cursor.get("document_index", 0)))
        engine_cursor = cast(
            JsonObject, session_cursor.get("engine_cursor", {"schema_version": 1})
        )
        engine_cursor = self._hydrate_engine_cursor(
            session_id, engine_cursor, exclude_call_key=exclude_call_key
        )
        session = self._session(session_id)
        target_kind = _object(session.snapshot_json).get("target_kind")
        request_json = self._request(session)
        rebuild_structure = request_json.get("rebuild_structure") is True
        while index < len(documents):
            item = documents[index]
            document_id = item["document_id"]
            text_revision_id = item["text_revision_id"]
            if document_id is None or text_revision_id is None:
                raise ValueError("EXTERNAL_DOCUMENT_SNAPSHOT_INVALID")
            current_row = self.connection.execute(
                "SELECT current_text_revision_id FROM style_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if target_kind == "reference_work" and (
                current_row is None or current_row[0] != item["text_revision_id"]
            ):
                session = self._session(session_id)
                self._append_episode_failure(
                    session,
                    index=index,
                    document_id=document_id,
                    error_code="DOCUMENT_REVISION_CHANGED",
                )
                index += 1
                engine_cursor = {"schema_version": 1}
                completed_call = None
                continue
            engine = ResumableDocumentAnalysisEngine(
                cast(Any, self.connection),
                model_provider=_PROVIDER,
                model_id=self._session(session_id).executor_model_id,
                policy=policy,
                run_observer=lambda run_id, role: self.repository.link_run(
                    session_id, run_id, role
                ),
            )
            request = DocumentAnalysisRequest(
                document_id=document_id,
                text_revision_id=text_revision_id,
                structure_revision_id=(
                    None
                    if item.get("structure_revision_id") is None
                    else item["structure_revision_id"]
                ),
                preset="full",
                rebuild_structure=rebuild_structure,
            )
            advanced = engine.advance(request, engine_cursor, completed_call)
            completed_call = None
            engine_cursor = advanced.cursor
            if advanced.pending_call is not None:
                return (
                    {
                        "schema_version": 1,
                        "document_index": index,
                        "documents": cast(JsonValue, documents),
                        "engine_cursor": self._safe_cursor(engine_cursor),
                    },
                    None,
                    advanced.pending_call,
                )
            if advanced.result is None:
                raise RuntimeError("external engine returned no result")
            index += 1
            engine_cursor = {"schema_version": 1}
            session = self._session(session_id)
            self._append_document_result(session, advanced.result, index, document_id)
        return (
            {
                "schema_version": 1,
                "document_index": index,
                "documents": cast(JsonValue, documents),
                "engine_cursor": self._safe_cursor(engine_cursor),
            },
            None,
            None,
        )

    def _hydrate_engine_cursor(
        self,
        session_id: int,
        cursor: JsonObject,
        *,
        exclude_call_key: str | None,
    ) -> JsonObject:
        value = dict(cursor)
        stage = value.get("stage")
        stage_runs = value.get("stage_runs", {})
        stage_run_id = stage_runs.get(stage) if isinstance(stage_runs, dict) else None
        scene_id = value.get("stage_scene_id")
        responses: list[JsonValue] = []
        if isinstance(stage, str) and isinstance(stage_run_id, int):
            for task in self.repository.list_tasks(session_id):
                if (
                    task.status != "accepted"
                    or task.response_json is None
                    or task.analysis_run_id != stage_run_id
                    or task.call_key == exclude_call_key
                ):
                    continue
                request = _object(task.request_json)
                payload = request.get("user_payload")
                if not isinstance(payload, dict):
                    continue
                if stage in {
                    "scene_boundary",
                    "entity_mentions",
                    "term_candidates",
                    "scene_semantics",
                    "pov",
                }:
                    if payload.get("scene_id") != scene_id:
                        continue
                    if (
                        stage in {"scene_semantics", "pov"}
                        and payload.get("mode") == "reduce"
                    ):
                        continue
                responses.append(cast(JsonValue, _object(task.response_json)))
        value["stage_responses"] = responses
        return value

    def _save_advance(
        self,
        *,
        session_id: int,
        cursor: JsonObject,
        result: Any | None,
        pending: PreparedModelCall | None,
        increment_version: bool,
    ) -> None:
        session = self._session(session_id)
        if pending is not None:
            self.repository.insert_task(
                session_id=session_id,
                sequence_no=self._next_sequence(session_id),
                prepared_call=pending,
            )
            status = "active"
            finished_at = None
        else:
            status = self._final_session_status(session, result)
            finished_at = _now()
        self.repository.update_session(
            session_id,
            status=cast(Any, status),
            cursor_json=cast(JsonValue, cursor),
            result_json=cast(JsonValue, self._result(session)),
            warning_json=cast(JsonValue, self._warnings(session)),
            error_code=None,
            error_message=None,
            finished_at=finished_at,
            increment_version=increment_version,
        )

    def _resume_after_submit(
        self,
        session: ExternalAnalysisSessionRecord,
        _task: ExternalAnalysisTaskRecord,
        completed: CompletedModelCall,
    ) -> None:
        request = self._request(session)
        policy = _policy(request.get("analysis_policy"))
        cursor = self._cursor(session)
        documents = cast(list[dict[str, int | None]], cursor["documents"])
        next_cursor, result, pending = self._advance_session(
            session_id=session.id,
            session_cursor=cursor,
            documents=documents,
            policy=policy,
            completed_call=completed,
            exclude_call_key=completed.call_key,
        )
        self._save_advance(
            session_id=session.id,
            cursor=next_cursor,
            result=result,
            pending=pending,
            increment_version=True,
        )

    def _reject_for_drift(
        self,
        session: ExternalAnalysisSessionRecord,
        task: ExternalAnalysisTaskRecord,
        response: JsonObject,
        code: str,
    ) -> None:
        self.repository.finalize_task(
            task_id=task.id,
            expected_version=task.version,
            status="rejected",
            response=response,
            error_codes=(code,),
        )
        runs = AnalysisRunRepository(cast(Any, self.connection))
        for link in self.repository.linked_runs(session.id):
            run = runs.get_run(link.run_id)
            if (
                link.run_role == "created"
                and run is not None
                and run.status == "running"
            ):
                runs.finish_run(run.id, status="failed", error_code=code)
        self.repository.update_session(
            session.id,
            status="failed",
            cursor_json=cast(JsonValue, self._cursor(session)),
            result_json=cast(JsonValue, self._result(session)),
            warning_json=cast(JsonValue, self._warnings(session)),
            error_code=code,
            error_message=code,
            finished_at=_now(),
        )

    def _repairable_errors(
        self, prepared: PreparedModelCall, response: JsonObject
    ) -> list[str]:
        validation_payload = prepared.user_payload
        original_request = prepared.user_payload.get("original_request")
        if isinstance(original_request, dict):
            validation_payload = cast(JsonObject, original_request)
        try:
            ResponseContractRegistry.validate(
                prepared.response_contract_id, response, validation_payload
            )
        except ValueError as exc:
            return [str(exc)]
        return []

    def _append_document_result(
        self,
        session: ExternalAnalysisSessionRecord,
        result: Any,
        index: int,
        document_id: int,
    ) -> None:
        values = self._result(session)
        episodes = values.setdefault("episodes", [])
        if isinstance(episodes, list):
            episodes.append(
                {
                    "document_index": index - 1,
                    "document_id": document_id,
                    "status": result.status,
                    "warnings": list(result.warnings),
                    "analysis_run_ids": list(result.run_ids),
                }
            )
        if result.status != "succeeded":
            values["status"] = "partial"
        session_result = cast(JsonValue, values)
        self.repository.update_session(
            session.id,
            status=cast(Any, session.status),
            cursor_json=cast(JsonValue, self._cursor(session)),
            result_json=session_result,
            warning_json=cast(JsonValue, self._warnings(session)),
            increment_version=False,
        )

    def _append_episode_failure(
        self,
        session: ExternalAnalysisSessionRecord,
        *,
        index: int,
        document_id: int,
        error_code: str,
    ) -> None:
        values = self._result(session)
        episodes = values.setdefault("episodes", [])
        if isinstance(episodes, list):
            episodes.append(
                {
                    "document_index": index,
                    "document_id": document_id,
                    "status": "failed",
                    "error_code": error_code,
                    "warnings": [error_code],
                    "analysis_run_ids": [],
                }
            )
        warnings = self._warnings(session)
        if error_code not in warnings:
            warnings.append(error_code)
        self.repository.update_session(
            session.id,
            status="active",
            cursor_json=cast(JsonValue, self._cursor(session)),
            result_json=cast(JsonValue, values),
            warning_json=cast(JsonValue, warnings),
            increment_version=False,
        )

    def _final_session_status(
        self, session: ExternalAnalysisSessionRecord, result: Any | None
    ) -> str:
        episode_values = cast(
            list[dict[str, object]], self._result(session).get("episodes", [])
        )
        statuses = [str(item.get("status")) for item in episode_values]
        if result is not None:
            statuses.append(result.status)
        if any(status in {"succeeded", "partial"} for status in statuses):
            return (
                "partial"
                if any(status != "succeeded" for status in statuses)
                else "succeeded"
            )
        return "failed"


def _prepared(task: ExternalAnalysisTaskRecord) -> PreparedModelCall:
    request = _object(task.request_json)
    return PreparedModelCall(
        call_key=task.call_key,
        analysis_run_id=task.analysis_run_id,
        analyzer_id=task.analyzer_id,
        analyzer_version=task.analyzer_version,
        prompt_id=task.prompt_id,
        prompt_version=task.prompt_version,
        response_contract_id=task.response_contract_id,
        system_prompt=str(request.get("system_prompt", "")),
        user_payload=cast(JsonObject, request.get("user_payload", {})),
        response_schema=cast(JsonObject, request.get("response_schema", {})),
    )


def _policy(value: object) -> AnalysisPolicy:
    if not isinstance(value, dict):
        raise ValueError("ANALYSIS_POLICY_SNAPSHOT_INVALID")
    fields = {field.name for field in AnalysisPolicy.__dataclass_fields__.values()}
    values = {key: value[key] for key in fields if key in value}
    if set(values) != fields:
        raise ValueError("ANALYSIS_POLICY_SNAPSHOT_INVALID")
    return AnalysisPolicy(**values)


def _object(value: str) -> JsonObject:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("EXTERNAL_JSON_OBJECT_REQUIRED")
    return cast(JsonObject, parsed)


def _list(value: str) -> list[object]:
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def _response_fingerprint(response: JsonObject) -> str:
    return hashlib.sha256(canonical_json_bytes(cast(JsonValue, response))).hexdigest()


def _positive(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(code)
    return value


def _optional_positive(value: object) -> int | None:
    return None if value is None else _positive(value, "ID_INVALID")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017
