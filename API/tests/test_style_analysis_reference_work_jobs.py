from __future__ import annotations

import json
from pathlib import Path

from test_style_analysis_jobs import _create_reference_analysis

from novel_api.style_analysis.execution import execute_style_job
from novel_api.style_analysis.job_service import StyleJobService


def test_reference_work_metrics_passes_snapshot_structure_to_document_analysis(
    data_root: Path,
) -> None:
    connection, document_id, _, _ = _create_reference_analysis(data_root)
    try:
        work_id = connection.execute(
            "SELECT reference_work_id FROM style_reference_episodes "
            "WHERE id = (SELECT reference_episode_id FROM style_documents "
            "WHERE id = ?)",
            (document_id,),
        ).fetchone()[0]
        cursor = connection.execute(
            "INSERT INTO style_jobs (job_type, payload_json, status) "
            "VALUES ('analyze_reference_work', ?, 'running')",
            (json.dumps({"reference_work_id": work_id, "preset": "metrics"}),),
        )
        assert cursor.lastrowid is not None
        connection.commit()
        row = connection.execute(
            "SELECT id, job_type, payload_json, status, cancel_requested, "
            "progress_current, progress_total, result_json, warning_json, created_at, "
            "started_at, finished_at, error_code, error_message, version "
            "FROM style_jobs WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        assert row is not None
        job = StyleJobService._record_from_row(row)
        execute_style_job(
            connection,
            job,
            model_client=None,
            model_provider=None,
            model_id=None,
        )
        assert connection.execute(
            "SELECT status FROM style_jobs WHERE id = ?", (job.id,)
        ).fetchone() == ("succeeded",)
        result = json.loads(
            connection.execute(
                "SELECT result_json FROM style_jobs WHERE id = ?", (job.id,)
            ).fetchone()[0]
        )
        assert result["episodes"][0]["status"] == "succeeded"
    finally:
        connection.close()
