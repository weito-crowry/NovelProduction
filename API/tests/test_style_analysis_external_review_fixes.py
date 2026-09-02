from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.external_analysis_runtime import (
    current_analysis_input_fingerprints,
)
from novel_core.style_analysis.runtime_models import AnalysisPolicy
from test_style_analysis_external_api import _document, _response_for_contract

from novel_api.style_analysis.job_service import StyleJobService


def test_external_submit_rejects_human_state_drift_and_is_idempotent(
    client: TestClient, data_root: Path
) -> None:
    document_id, text_revision_id = _document(client, data_root)
    base = "/api/v1/projects/external/style-analysis"
    started = client.post(
        f"{base}/external-sessions",
        json={
            "target": {
                "kind": "document",
                "document_id": document_id,
                "text_revision_id": text_revision_id,
            },
            "executor_model_id": "gpt-test",
        },
    )
    assert started.status_code == 201
    snapshot = started.json()["data"]

    while snapshot["task"]["analyzer_id"] != "entity-resolver":
        task = snapshot["task"]
        response = _response_for_contract(task["response_contract_id"])
        if task["analyzer_id"] == "entity-mention-extractor":
            block = task["user_payload"]["blocks"][0]
            text = block["text"]
            response = {
                "mentions": [
                    {
                        "block_id": block["block_id"],
                        "surface": text[:1],
                        "start_in_block": 0,
                        "end_in_block": 1,
                        "mention_type": "proper_name",
                        "entity_type_candidate": "person",
                        "canonical_name_candidate": text[:1],
                        "confidence": 0.9,
                    }
                ]
            }
        submitted = client.post(
            f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
            f"{task['task_id']}/submit",
            json={
                "expected_task_version": task["task_version"],
                "executor_model_id": "gpt-test",
                "response": response,
            },
        )
        assert submitted.status_code == 200
        snapshot = submitted.json()["data"]

    task = snapshot["task"]
    response = {
        "decision": "unresolved",
        "entity_id": None,
        "new_entity_type": None,
        "new_canonical_name": None,
        "confidence": 0.1,
    }
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        run_id = task["analysis_run_id"]
        run_before = AnalysisRunRepository(connection).get_run(run_id)
        assert run_before is not None
        before_state = run_before.state_fingerprint
        work_id = connection.execute(
            "SELECT reference_work_id FROM style_reference_episodes "
            "WHERE id = (SELECT reference_episode_id FROM style_documents "
            "WHERE id = ?)",
            (document_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO style_entities "
            "(reference_work_id, entity_type, canonical_name, origin) "
            "VALUES (?, 'person', 'Human correction', 'manual')",
            (work_id,),
        )
        connection.commit()
        after_state, _ = current_analysis_input_fingerprints(
            connection, AnalysisPolicy(), run_id
        )
        assert before_state != after_state
    finally:
        connection.close()

    rejected = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
        f"{task['task_id']}/submit",
        json={
            "expected_task_version": task["task_version"],
            "executor_model_id": "gpt-test",
            "response": response,
        },
    )
    assert rejected.status_code == 200
    failed = rejected.json()["data"]
    assert failed["status"] == "failed"
    assert failed["error_code"] == "EXTERNAL_ANALYSIS_INPUT_CHANGED"

    retry = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
        f"{task['task_id']}/submit",
        json={
            "expected_task_version": 1,
            "executor_model_id": "gpt-test",
            "response": response,
        },
    )
    assert retry.status_code == 200
    assert retry.json()["data"]["version"] == failed["version"]

    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        row = connection.execute(
            "SELECT status, response_json FROM style_external_analysis_tasks "
            "WHERE id = ?",
            (task["task_id"],),
        ).fetchone()
        assert row is not None
        assert row[0] == "rejected"
        assert json.loads(row[1]) == response
    finally:
        connection.close()


def test_retry_internal_analysis_job_conflicts_with_active_external_session(
    client: TestClient, data_root: Path
) -> None:
    document_id, text_revision_id = _document(client, data_root)
    jobs = StyleJobService(data_root=data_root)
    original = jobs.enqueue(
        "external",
        "analyze_document",
        {"document_id": document_id, "text_revision_id": text_revision_id},
    )
    jobs.set_status("external", original.id, "failed")
    started = client.post(
        "/api/v1/projects/external/style-analysis/external-sessions",
        json={
            "target": {
                "kind": "document",
                "document_id": document_id,
                "text_revision_id": text_revision_id,
            },
            "executor_model_id": "gpt-test",
        },
    )
    assert started.status_code == 201

    before = jobs.get("external", original.id)
    assert before is not None
    retry = client.post(
        f"/api/v1/projects/external/style-analysis/jobs/{original.id}/retry"
    )
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "ANALYSIS_EXECUTION_CONFLICT"
    after = jobs.get("external", original.id)
    assert after is not None
    assert after == before


def test_purge_reference_work_conflicts_without_mutating_source_graph(
    client: TestClient, data_root: Path
) -> None:
    created = client.post(
        "/api/v1/projects",
        json={"project_id": "external", "working_title": "External"},
    )
    assert created.status_code == 201
    imported = client.post(
        "/api/v1/projects/external/style-analysis/imports/file",
        data={"source_type": "text"},
        files={"file": ("reference.txt", "参考本文".encode(), "text/plain")},
    )
    assert imported.status_code == 201
    work_id = imported.json()["data"]["reference_work_id"]
    started = client.post(
        "/api/v1/projects/external/style-analysis/external-sessions",
        json={
            "target": {"kind": "reference_work", "reference_work_id": work_id},
            "executor_model_id": "gpt-test",
        },
    )
    assert started.status_code == 201

    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        before = connection.execute(
            "SELECT COUNT(*) FROM style_reference_works WHERE id = ?", (work_id,)
        ).fetchone()[0]
        session_count = connection.execute(
            "SELECT COUNT(*) FROM style_external_analysis_sessions "
            "WHERE reference_work_id = ?",
            (work_id,),
        ).fetchone()[0]
    finally:
        connection.close()

    purge = client.delete(
        f"/api/v1/projects/external/style-analysis/reference-works/{work_id}"
    )
    assert purge.status_code == 409
    assert purge.json()["error"]["code"] == "ANALYSIS_EXECUTION_CONFLICT"

    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_reference_works WHERE id = ?", (work_id,)
            ).fetchone()[0]
            == before
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_external_analysis_sessions "
                "WHERE reference_work_id = ?",
                (work_id,),
            ).fetchone()[0]
            == session_count
        )
    finally:
        connection.close()


def test_external_multichunk_scene_and_pov_resume_from_persisted_task_history(
    client: TestClient, data_root: Path
) -> None:
    document_id, text_revision_id = _document(client, data_root)
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        structure_id = connection.execute(
            "SELECT current_structure_revision_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()[0]
        scene_id = connection.execute(
            "SELECT id FROM style_scenes WHERE structure_revision_id = ?",
            (structure_id,),
        ).fetchone()[0]
        first_block_id = connection.execute(
            "SELECT id FROM style_blocks WHERE structure_revision_id = ? "
            "ORDER BY order_index LIMIT 1",
            (structure_id,),
        ).fetchone()[0]
        text = "a" * 16000 + "b" * 16000
        connection.execute(
            "UPDATE style_text_revisions SET raw_text = ?, canonical_text = ? "
            "WHERE id = ?",
            (text, text, text_revision_id),
        )
        connection.execute(
            "UPDATE style_scenes SET end_cp = ? WHERE id = ?",
            (len(text), scene_id),
        )
        connection.execute(
            "UPDATE style_blocks SET end_cp = ? WHERE id = ?",
            (16000, first_block_id),
        )
        connection.execute(
            "INSERT INTO style_blocks "
            "(structure_revision_id, scene_id, order_index, paragraph_index, "
            "block_type, start_cp, end_cp) VALUES (?, ?, 2, 2, 'narration', ?, ?)",
            (structure_id, scene_id, 16000, len(text)),
        )
        connection.commit()
    finally:
        connection.close()

    base = "/api/v1/projects/external/style-analysis"
    started = client.post(
        f"{base}/external-sessions",
        json={
            "target": {
                "kind": "document",
                "document_id": document_id,
                "text_revision_id": text_revision_id,
                "structure_revision_id": structure_id,
            },
            "executor_model_id": "gpt-test",
        },
    )
    assert started.status_code == 201
    snapshot = started.json()["data"]
    calls: list[dict[str, object]] = []
    repaired_scene_semantic_call_key: str | None = None
    reduce_chunks: list[object] | None = None
    while snapshot["status"] == "active":
        task = snapshot["task"]
        assert task is not None
        calls.append(task)
        response = _response_for_contract(task["response_contract_id"])
        if task["analyzer_id"] == "scene-semantic-classifier":
            if task["user_payload"].get("mode") == "reduce":
                reduce_chunks = task["user_payload"]["chunks"]
                response = {
                    "pace": {"label": "medium", "confidence": 0.8},
                    "information_load": {"label": "low", "confidence": 0.8},
                    "interaction": {"label": "solo", "confidence": 0.8},
                }
            elif task["attempt_no"] == 1 and repaired_scene_semantic_call_key is None:
                response = {}
            else:
                if task["attempt_no"] == 2:
                    repaired_scene_semantic_call_key = str(task["call_key"])
                response = {
                    "function": [{"label": "daily", "confidence": 0.8}],
                    "tone": [{"label": "calm", "confidence": 0.8}],
                    "pace": {"label": "medium", "confidence": 0.8},
                    "information_load": {"label": "low", "confidence": 0.8},
                    "interaction": {"label": "solo", "confidence": 0.8},
                }
        if task["analyzer_id"] == "pov-classifier":
            response = {
                "pov_mode": "unclear",
                "pov_entity_id": None,
                "confidence": 0.2,
            }
        submitted = client.post(
            f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
            f"{task['task_id']}/submit",
            json={
                "expected_task_version": task["task_version"],
                "executor_model_id": "gpt-test",
                "response": response,
            },
        )
        assert submitted.status_code == 200
        snapshot = client.get(
            f"{base}/external-sessions/{snapshot['session_id']}"
        ).json()["data"]
        assert len(calls) < 30

    pov_calls = [item for item in calls if item["analyzer_id"] == "pov-classifier"]
    assert [item["user_payload"].get("mode") for item in pov_calls] == [
        "classify",
        "classify",
        "reduce",
    ]
    assert len(pov_calls[-1]["user_payload"]["chunks"]) == 2
    assert "scene_id" not in pov_calls[-1]["user_payload"]
    semantic_calls = []
    for item in calls:
        if item["analyzer_id"] != "scene-semantic-classifier":
            continue
        payload = item["user_payload"]
        original_request = payload.get("original_request")
        if isinstance(original_request, dict):
            payload = original_request
        if item["attempt_no"] != 2 and payload.get("mode") in {
            "classify",
            "reduce",
        }:
            semantic_calls.append(item)
    semantic_modes = []
    for item in semantic_calls:
        payload = item["user_payload"]
        original_request = payload.get("original_request")
        if isinstance(original_request, dict):
            payload = original_request
        semantic_modes.append(payload.get("mode"))
    assert semantic_modes == ["classify", "classify", "reduce"]
    assert repaired_scene_semantic_call_key is not None
    assert reduce_chunks is not None
    assert len(reduce_chunks) == 2
    assert all(isinstance(chunk, dict) for chunk in reduce_chunks)
    assert snapshot["status"] == "succeeded"

    result_entry = snapshot["result"]["episodes"][0]
    assert result_entry["document_id"] == document_id
    assert result_entry["text_revision_id"] == text_revision_id
    assert result_entry["structure_revision_id"] == structure_id
    metrics = client.get(
        f"{base}/documents/{document_id}/metrics",
        params={"structure_revision_id": structure_id},
    )
    assert metrics.status_code == 200

    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_annotations WHERE annotation_type IN "
                "('scene.pov', 'scene.function', 'scene.tone', 'scene.pace', "
                "'scene.information_load', 'scene.interaction') AND subject_id = ?",
                (scene_id,),
            ).fetchone()[0]
            == 6
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_annotations WHERE subject_id = 0"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


def test_external_pov_allowlisted_entity_accepts_repair_response(
    client: TestClient, data_root: Path
) -> None:
    document_id, text_revision_id = _document(client, data_root)
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        work_id = connection.execute(
            "SELECT reference_work_id FROM style_reference_episodes "
            "WHERE id = (SELECT reference_episode_id FROM style_documents "
            "WHERE id = ?)",
            (document_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO style_entities "
            "(reference_work_id, entity_type, canonical_name, origin) "
            "VALUES (?, 'person', 'POV Person', 'manual')",
            (work_id,),
        )
        entity_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.commit()
    finally:
        connection.close()

    base = "/api/v1/projects/external/style-analysis"
    started = client.post(
        f"{base}/external-sessions",
        json={
            "target": {
                "kind": "document",
                "document_id": document_id,
                "text_revision_id": text_revision_id,
            },
            "executor_model_id": "gpt-test",
        },
    )
    assert started.status_code == 201
    snapshot = started.json()["data"]
    while snapshot["task"]["analyzer_id"] != "pov-classifier":
        task = snapshot["task"]
        response = _response_for_contract(task["response_contract_id"])
        if task["analyzer_id"] == "entity-mention-extractor":
            block = task["user_payload"]["blocks"][0]
            response = {
                "mentions": [
                    {
                        "block_id": block["block_id"],
                        "surface": block["text"][:1],
                        "start_in_block": 0,
                        "end_in_block": 1,
                        "mention_type": "proper_name",
                        "entity_type_candidate": "person",
                        "canonical_name_candidate": "POV Person",
                        "confidence": 0.9,
                    }
                ]
            }
        elif task["analyzer_id"] == "entity-resolver":
            response = {
                "decision": "existing",
                "entity_id": entity_id,
                "new_entity_type": None,
                "new_canonical_name": None,
                "confidence": 0.9,
            }
        submitted = client.post(
            f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
            f"{task['task_id']}/submit",
            json={
                "expected_task_version": task["task_version"],
                "executor_model_id": "gpt-test",
                "response": response,
            },
        )
        assert submitted.status_code == 200
        snapshot = submitted.json()["data"]

    initial = snapshot["task"]
    people = initial["user_payload"]["people"]
    assert {person["entity_id"] for person in people} == {entity_id}
    invalid = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
        f"{initial['task_id']}/submit",
        json={
            "expected_task_version": initial["task_version"],
            "executor_model_id": "gpt-test",
            "response": {
                "pov_mode": "third_limited",
                "pov_entity_id": 999,
                "confidence": 0.9,
            },
        },
    )
    assert invalid.status_code == 200
    repair_task = invalid.json()["data"]["task"]
    assert repair_task["attempt_no"] == 2
    valid = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
        f"{repair_task['task_id']}/submit",
        json={
            "expected_task_version": repair_task["task_version"],
            "executor_model_id": "gpt-test",
            "response": {
                "pov_mode": "third_limited",
                "pov_entity_id": entity_id,
                "confidence": 0.9,
            },
        },
    )
    assert valid.status_code == 200
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        assert connection.execute(
            "SELECT status FROM style_external_analysis_tasks WHERE id = ?",
            (repair_task["task_id"],),
        ).fetchone() == ("accepted",)
    finally:
        connection.close()
