from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from novel_core.errors import AnalysisCancelledError
from novel_core.style_analysis.aggregate_service import AggregateService
from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.corpus_models import AggregateSpec
from novel_core.style_analysis.lint_service import StyleLintService
from novel_core.style_analysis.model_contracts import ModelClient
from novel_core.style_analysis.runtime_models import JobRecord

from novel_api.style_analysis.job_service import DatabaseConnection


def execute_style_job(
    connection: DatabaseConnection,
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
                connection, job.id, payload, model_client, model_provider, model_id
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
        elif job.job_type == "recompute_aggregate":
            _aggregate(connection, job, payload)
        elif job.job_type == "run_lint":
            result = _lint(connection, job, payload)
            _store_result(
                connection,
                job.id,
                "succeeded",
                json.loads(result.run.warning_json),
                {
                    "lint_run_id": result.run.id,
                    "coverage_ratio": result.run.coverage_ratio,
                    "enabled_rule_count": result.run.enabled_rule_count,
                    "applicable_rule_count": result.run.applicable_rule_count,
                    "missing_rule_count": result.run.missing_rule_count,
                },
            )
        else:
            _fail(connection, job.id, "JOB_TYPE_NOT_IMPLEMENTED", job.job_type)
    except AnalysisCancelledError:
        connection.rollback()
        _cancel(connection, job.id)
    except ValueError as exc:
        connection.rollback()
        _fail(connection, job.id, str(exc), str(exc))
    except Exception as exc:
        connection.rollback()
        _fail(connection, job.id, "WORKER_EXECUTION_FAILED", str(exc))


def _document(
    connection: DatabaseConnection,
    job_id: int,
    payload: Mapping[str, object],
    model_client: ModelClient | None,
    provider: str | None,
    model_id: str | None,
) -> Any:
    document_id = _positive_int(payload.get("document_id"), "DOCUMENT_ID_REQUIRED")
    text_revision_id = _optional_positive_int(payload.get("text_revision_id"))
    structure_revision_id = _optional_positive_int(payload.get("structure_revision_id"))
    preset = payload.get("preset", "full")
    if preset not in {"deterministic", "full", "metrics"}:
        raise ValueError("ANALYSIS_PRESET_INVALID")
    orchestrator = DocumentAnalysisOrchestrator(
        cast(Any, connection),
        model_client=model_client,
        model_provider=provider,
        model_id=model_id,
        cancellation_probe=lambda: _is_cancel_requested(connection, job_id),
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
    connection: DatabaseConnection,
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
        "SELECT re.id, sd.id, sd.current_text_revision_id, "
        "sd.current_structure_revision_id "
        "FROM style_reference_episodes re "
        "JOIN style_documents sd ON sd.reference_episode_id = re.id "
        "WHERE re.reference_work_id = ? ORDER BY re.order_index",
        (work_id,),
    ).fetchall()
    if not rows:
        raise ValueError("REFERENCE_WORK_NOT_FOUND")
    rebuild_structure = payload.get("rebuild_structure", False)
    if not isinstance(rebuild_structure, bool):
        raise ValueError("REBUILD_STRUCTURE_INVALID")
    orchestrator = DocumentAnalysisOrchestrator(
        cast(Any, connection),
        model_client=model_client,
        model_provider=provider,
        model_id=model_id,
        cancellation_probe=lambda: _is_cancel_requested(connection, job.id),
    )
    statuses: list[str] = []
    results: list[dict[str, object]] = []
    warnings: list[str] = []
    total = len(rows)
    connection.execute(
        "UPDATE style_jobs SET progress_current = 0, progress_total = ? WHERE id = ?",
        (total, job.id),
    )
    connection.commit()
    for index, (
        episode_id,
        document_id,
        text_revision_id,
        structure_revision_id,
    ) in enumerate(rows, start=1):
        state = connection.execute(
            "SELECT cancel_requested FROM style_jobs WHERE id = ?", (job.id,)
        ).fetchone()
        if state is not None and state[0]:
            _cancel(connection, job.id)
            return
        current = connection.execute(
            "SELECT current_text_revision_id, current_structure_revision_id "
            "FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        structure_matches = preset != "metrics" or (
            current is not None
            and current[1] is not None
            and current[1] == structure_revision_id
        )
        if current is None or current[0] != text_revision_id or not structure_matches:
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
                structure_revision_id=(
                    structure_revision_id if preset == "metrics" else None
                ),
                preset=preset,
                rebuild_structure=rebuild_structure,
            )
            if _is_cancel_requested(connection, job.id):
                _cancel(connection, job.id)
                return
            after = connection.execute(
                "SELECT current_text_revision_id, current_structure_revision_id "
                "FROM style_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            after_structure_matches = preset != "metrics" or (
                after is not None
                and after[1] is not None
                and after[1] == structure_revision_id
            )
            if (
                after is None
                or after[0] != text_revision_id
                or not after_structure_matches
            ):
                statuses.append("failed")
                warnings.append(f"DOCUMENT_REVISION_CHANGED:{episode_id}")
                results.append(
                    {
                        "episode_id": episode_id,
                        "status": "failed",
                        "error_code": "DOCUMENT_REVISION_CHANGED",
                        "analysis_run_ids": list(result.run_ids),
                    }
                )
            else:
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
        connection.commit()
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


def _aggregate(
    connection: DatabaseConnection,
    job: JobRecord,
    payload: Mapping[str, object],
) -> None:
    container_type = payload.get("container_type")
    if container_type not in {"reference_work", "corpus"}:
        raise ValueError("AGGREGATE_CONTAINER_INVALID")
    container_id = _positive_int(payload.get("container_id"), "CONTAINER_ID_REQUIRED")
    target_type = payload.get("measurement_target_type")
    if target_type not in {"document", "scene"}:
        raise ValueError("AGGREGATE_TARGET_INVALID")
    raw_filter = payload.get("filter", {})
    if not isinstance(raw_filter, dict):
        raise ValueError("AGGREGATE_FILTER_INVALID")
    metric_names = payload.get("metric_names")
    if (
        not isinstance(metric_names, list)
        or not metric_names
        or any(not isinstance(name, str) for name in metric_names)
    ):
        raise ValueError("METRIC_NAMES_REQUIRED")
    filter_json = json.dumps(
        raw_filter,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    connection.execute(
        "UPDATE style_jobs SET progress_current = 0, progress_total = ? WHERE id = ?",
        (len(metric_names), job.id),
    )
    connection.commit()
    service = AggregateService(cast(Any, connection))
    result = service.recompute(
        (
            AggregateSpec(
                cast(Any, container_type),
                container_id,
                cast(Any, target_type),
                filter_json,
                metric_names[0],
                1,
            ),
        ),
        tuple(metric_names),
    )
    connection.execute(
        "UPDATE style_jobs SET progress_current = ? WHERE id = ?",
        (len(metric_names), job.id),
    )
    aggregate_ids: dict[str, dict[str, int]] = {}
    for aggregate in result.aggregates:
        aggregate_ids.setdefault(aggregate.metric_name, {})[aggregate.statistic] = (
            aggregate.id
        )
    _store_result(
        connection,
        job.id,
        "succeeded",
        result.warnings,
        {
            "container_type": container_type,
            "container_id": container_id,
            "aggregates": aggregate_ids,
        },
    )


def _lint(
    connection: DatabaseConnection,
    job: JobRecord,
    payload: Mapping[str, object],
) -> Any:
    document_id = _positive_int(payload.get("document_id"), "DOCUMENT_ID_REQUIRED")
    text_revision_id = _positive_int(
        payload.get("text_revision_id"), "TEXT_REVISION_ID_REQUIRED"
    )
    structure_revision_id = _positive_int(
        payload.get("structure_revision_id"), "STRUCTURE_REVISION_ID_REQUIRED"
    )
    profile_id = _positive_int(payload.get("profile_id"), "PROFILE_ID_REQUIRED")
    profile_version_no = _positive_int(
        payload.get("profile_version_no"), "PROFILE_VERSION_NO_REQUIRED"
    )
    scene_id = payload.get("scene_id")
    if scene_id is not None:
        scene_id = _positive_int(scene_id, "SCENE_ID_INVALID")
    connection.execute(
        "UPDATE style_jobs SET progress_current = 0, progress_total = 0 WHERE id = ?",
        (job.id,),
    )
    connection.commit()
    if _is_cancel_requested(connection, job.id):
        _cancel(connection, job.id)
        raise AnalysisCancelledError()

    def report_progress(current: int, total: int) -> None:
        connection.execute(
            "UPDATE style_jobs SET progress_current = ?, progress_total = ? "
            "WHERE id = ?",
            (current, total, job.id),
        )
        connection.commit()

    result = StyleLintService(cast(Any, connection)).run(
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        profile_id=profile_id,
        profile_version_no=profile_version_no,
        scene_id=scene_id,
        progress_callback=report_progress,
        cancellation_probe=lambda: _is_cancel_requested(connection, job.id),
    )
    if _is_cancel_requested(connection, job.id):
        raise AnalysisCancelledError()
    connection.execute(
        "UPDATE style_jobs SET progress_current = progress_total WHERE id = ?",
        (job.id,),
    )
    return result


def _store_result(
    connection: DatabaseConnection,
    job_id: int,
    status: str,
    warnings: tuple[str, ...] | list[str],
    result: Mapping[str, object],
) -> None:
    connection.execute(
        "UPDATE style_jobs SET status = ?, result_json = ?, "
        "warning_json = ?, finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP) "
        "WHERE id = ?",
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


def _fail(connection: DatabaseConnection, job_id: int, code: str, message: str) -> None:
    connection.execute(
        "UPDATE style_jobs SET status='failed', error_code=?, "
        "error_message=?, finished_at=CURRENT_TIMESTAMP WHERE id = ?",
        (code, message, job_id),
    )


def _is_cancel_requested(connection: DatabaseConnection, job_id: int) -> bool:
    row = connection.execute(
        "SELECT cancel_requested FROM style_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    return row is not None and bool(row[0])


def _cancel(connection: DatabaseConnection, job_id: int) -> None:
    connection.execute(
        "UPDATE style_jobs SET status = 'cancelled', "
        "finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP) WHERE id = ?",
        (job_id,),
    )
    connection.commit()


def _positive_int(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(code)
    return value


def _optional_positive_int(value: object) -> int | None:
    return None if value is None else _positive_int(value, "ID_INVALID")
