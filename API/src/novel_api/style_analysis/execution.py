from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.model_contracts import ModelClient
from novel_core.style_analysis.runtime_models import JobRecord


def execute_style_job(
    connection: sqlite3.Connection,
    job: JobRecord,
    *,
    model_client: ModelClient | None,
    model_provider: str | None,
    model_id: str | None,
) -> None:
    try:
        payload = json.loads(job.payload_json)
    except json.JSONDecodeError as exc:
        _fail(connection, job.id, "JOB_PAYLOAD_INVALID", str(exc))
        return
    if not isinstance(payload, dict):
        _fail(connection, job.id, "JOB_PAYLOAD_INVALID", "payload must be an object")
        return
    try:
        if job.job_type == "analyze_document":
            result = _document(
                connection, payload, model_client, model_provider, model_id
            )
            _store_result(
                connection,
                job.id,
                result.status,
                result.warnings,
                {
                    "text_revision_id": result.text_revision_id,
                    "structure_revision_id": result.structure_revision_id,
                    "analysis_run_ids": list(result.run_ids),
                    "metrics": list(result.metrics),
                },
            )
        elif job.job_type == "analyze_reference_work":
            _work(connection, job, payload, model_client, model_provider, model_id)
        else:
            _fail(connection, job.id, "JOB_TYPE_NOT_IMPLEMENTED", job.job_type)
    except ValueError as exc:
        _fail(connection, job.id, str(exc), str(exc))
    except Exception as exc:
        _fail(connection, job.id, "WORKER_EXECUTION_FAILED", str(exc))


def _document(
    connection: sqlite3.Connection,
    payload: Mapping[str, object],
    model_client: ModelClient | None,
    provider: str | None,
    model_id: str | None,
) -> Any:
    document_id = _positive_int(payload.get("document_id"), "DOCUMENT_ID_REQUIRED")
    text_revision_id = _optional_positive_int(payload.get("text_revision_id"))
    structure_revision_id = _optional_positive_int(payload.get("structure_revision_id"))
    preset = payload.get("preset", "full")
    if preset not in {"deterministic", "full"}:
        raise ValueError("ANALYSIS_PRESET_INVALID")
    orchestrator = DocumentAnalysisOrchestrator(
        connection,
        model_client=model_client,
        model_provider=provider,
        model_id=model_id,
    )
    rebuild_structure = payload.get("rebuild_structure", False)
    if not isinstance(rebuild_structure, bool):
        raise ValueError("REBUILD_STRUCTURE_INVALID")
    return orchestrator.analyze_document(
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        preset=str(preset),
        rebuild_structure=rebuild_structure,
    )


def _work(
    connection: sqlite3.Connection,
    job: JobRecord,
    payload: Mapping[str, object],
    model_client: ModelClient | None,
    provider: str | None,
    model_id: str | None,
) -> None:
    work_id = _positive_int(
        payload.get("reference_work_id"), "REFERENCE_WORK_ID_REQUIRED"
    )
    preset = str(payload.get("preset", "full"))
    rows = connection.execute(
        "SELECT re.id, sd.id, sd.current_text_revision_id "
        "FROM style_reference_episodes re "
        "JOIN style_documents sd ON sd.reference_episode_id = re.id "
        "WHERE re.reference_work_id = ? ORDER BY re.order_index",
        (work_id,),
    ).fetchall()
    if not rows:
        raise ValueError("REFERENCE_WORK_NOT_FOUND")
    orchestrator = DocumentAnalysisOrchestrator(
        connection,
        model_client=model_client,
        model_provider=provider,
        model_id=model_id,
    )
    statuses: list[str] = []
    results: list[dict[str, object]] = []
    warnings: list[str] = []
    total = len(rows)
    connection.execute(
        "UPDATE style_jobs SET progress_current = 0, progress_total = ? WHERE id = ?",
        (total, job.id),
    )
    for index, (episode_id, document_id, text_revision_id) in enumerate(rows, start=1):
        state = connection.execute(
            "SELECT cancel_requested FROM style_jobs WHERE id = ?", (job.id,)
        ).fetchone()
        if state is not None and state[0]:
            connection.execute(
                "UPDATE style_jobs SET status='cancelled', "
                "finished_at=CURRENT_TIMESTAMP WHERE id = ?",
                (job.id,),
            )
            return
        current = connection.execute(
            "SELECT current_text_revision_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if current is None or current[0] != text_revision_id:
            statuses.append("failed")
            warnings.append(f"DOCUMENT_REVISION_CHANGED:{episode_id}")
            results.append(
                {
                    "episode_id": episode_id,
                    "status": "failed",
                    "error_code": "DOCUMENT_REVISION_CHANGED",
                }
            )
        else:
            result = orchestrator.analyze_document(
                document_id=document_id,
                text_revision_id=text_revision_id,
                preset=preset,
            )
            statuses.append(result.status)
            warnings.extend(result.warnings)
            results.append(
                {
                    "episode_id": episode_id,
                    "status": result.status,
                    "analysis_run_ids": list(result.run_ids),
                }
            )
        connection.execute(
            "UPDATE style_jobs SET progress_current = ? WHERE id = ?", (index, job.id)
        )
    final = (
        "succeeded"
        if all(status == "succeeded" for status in statuses)
        else "partial"
        if any(status != "failed" for status in statuses)
        else "failed"
    )
    _store_result(
        connection,
        job.id,
        final,
        warnings,
        {"reference_work_id": work_id, "episodes": results},
    )


def _store_result(
    connection: sqlite3.Connection,
    job_id: int,
    status: str,
    warnings: tuple[str, ...] | list[str],
    result: Mapping[str, object],
) -> None:
    connection.execute(
        "UPDATE style_jobs SET status = ?, result_json = ?, "
        "warning_json = ? WHERE id = ?",
        (
            status,
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            json.dumps(
                list(warnings),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ),
            job_id,
        ),
    )


def _fail(connection: sqlite3.Connection, job_id: int, code: str, message: str) -> None:
    connection.execute(
        "UPDATE style_jobs SET status='failed', error_code=?, "
        "error_message=?, finished_at=CURRENT_TIMESTAMP WHERE id = ?",
        (code, message, job_id),
    )


def _positive_int(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(code)
    return value


def _optional_positive_int(value: object) -> int | None:
    return None if value is None else _positive_int(value, "ID_INVALID")
