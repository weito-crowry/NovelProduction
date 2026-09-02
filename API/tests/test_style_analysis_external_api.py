from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.structure_service import StyleStructureService


def _response_for_contract(contract_id: str) -> dict[str, object]:
    label = {"label": "unclear", "confidence": 0.1}
    if contract_id == "style.entity_mentions.v1":
        return {"mentions": []}
    if contract_id == "style.term_candidates.v1":
        return {"terms": []}
    if contract_id == "style.scene_semantics.classify.v1":
        return {
            "function": [label],
            "tone": [label],
            "pace": label,
            "information_load": label,
            "interaction": label,
        }
    if contract_id == "style.scene_semantics.reduce.v1":
        return {"pace": label, "information_load": label, "interaction": label}
    if contract_id == "style.block_semantic.v1":
        return label
    if contract_id == "style.pov.v1":
        return {"pov_mode": "unclear", "pov_entity_id": None, "confidence": 0.1}
    if contract_id == "style.speaker_attribution.v1":
        return {
            "speaker_entity_id": None,
            "confidence": 0.1,
            "evidence_block_ids": [],
            "reason_code": "unknown",
        }
    if contract_id == "style.term_explanation.v1":
        return {"explanations": []}
    if contract_id == "style.entity_resolution.v1":
        return {
            "decision": "unresolved",
            "entity_id": None,
            "new_entity_type": None,
            "new_canonical_name": None,
            "confidence": 0.1,
        }
    if contract_id == "style.term_resolution.v1":
        return {
            "decision": "unresolved",
            "term_id": None,
            "new_term_type": None,
            "new_canonical_label": None,
            "confidence": 0.1,
        }
    if contract_id == "style.scene_boundary.v1":
        return {"boundaries": []}
    raise AssertionError(contract_id)


def _document(client: TestClient, data_root: Path) -> tuple[int, int]:
    created = client.post(
        "/api/v1/projects",
        json={"project_id": "external", "working_title": "External"},
    )
    assert created.status_code == 201
    imported = client.post(
        "/api/v1/projects/external/style-analysis/imports/file",
        data={"source_type": "text"},
        files={"file": ("episode.txt", "本文。".encode(), "text/plain")},
    )
    assert imported.status_code == 201
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        row = connection.execute(
            "SELECT id, current_text_revision_id FROM style_documents "
            "WHERE reference_episode_id IS NOT NULL"
        ).fetchone()
        assert row is not None
        document_id, text_revision_id = map(int, row)
        result = DocumentAnalysisOrchestrator(
            connection, model_client=None
        ).analyze_document(
            document_id=document_id,
            text_revision_id=text_revision_id,
            preset="deterministic",
        )
        connection.commit()
        assert result.structure_revision_id > 0
        return document_id, text_revision_id
    finally:
        connection.close()

def test_external_session_start_submit_idempotency_and_cancel(
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
    assert snapshot["status"] == "active"
    task = snapshot["task"]
    assert task["task_id"] > 0
    assert task["attempt_no"] == 1

    mismatch = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/tasks/{task['task_id']}/submit",
        json={
            "expected_task_version": task["task_version"],
            "executor_model_id": "other-model",
            "response": {"mentions": []},
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "EXTERNAL_EXECUTOR_MISMATCH"

    submitted = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/tasks/{task['task_id']}/submit",
        json={
            "expected_task_version": task["task_version"],
            "executor_model_id": "gpt-test",
            "response": {"mentions": []},
        },
    )
    assert submitted.status_code == 200
    submitted_snapshot = submitted.json()["data"]
    assert submitted_snapshot["version"] == snapshot["version"] + 1

    retry = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/tasks/{task['task_id']}/submit",
        json={
            "expected_task_version": 1,
            "executor_model_id": "gpt-test",
            "response": {"mentions": []},
        },
    )
    assert retry.status_code == 200
    assert retry.json()["data"]["version"] == submitted_snapshot["version"]

    cancelled = client.post(
        f"{base}/external-sessions/{snapshot['session_id']}/cancel",
        json={"expected_session_version": submitted_snapshot["version"]},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"


def test_external_session_repair_creates_one_retry_task(
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
    initial = started.json()["data"]
    task = initial["task"]

    repair = client.post(
        f"{base}/external-sessions/{initial['session_id']}/tasks/"
        f"{task['task_id']}/submit",
        json={
            "expected_task_version": task["task_version"],
            "executor_model_id": "gpt-test",
            "response": {},
        },
    )
    assert repair.status_code == 200
    repair_snapshot = repair.json()["data"]
    repair_task = repair_snapshot["task"]
    assert repair_task["attempt_no"] == 2
    assert repair_task["call_key"] == task["call_key"]
    assert repair_task["response_contract_id"] == task["response_contract_id"]
    assert repair_task["validation_errors"]
    assert repair_task["user_payload"]["invalid_response"] == "{}"
    assert repair_task["user_payload"]["validation_errors"]

    completed = client.post(
        f"{base}/external-sessions/{initial['session_id']}/tasks/"
        f"{repair_task['task_id']}/submit",
        json={
            "expected_task_version": repair_task["task_version"],
            "executor_model_id": "gpt-test",
            "response": {"mentions": []},
        },
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["task"]["attempt_no"] == 1


def test_external_start_persists_and_honors_rebuild_structure(
    client: TestClient, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document_id, text_revision_id = _document(client, data_root)
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        before = connection.execute(
            "SELECT current_structure_revision_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        assert before is not None
        old_structure_id = before[0]
    finally:
        connection.close()

    build_calls: list[dict[str, object]] = []
    original_build = StyleStructureService.build_automatic_structure

    def record_build(self: StyleStructureService, **kwargs: object):
        build_calls.append(dict(kwargs))
        return original_build(self, **kwargs)

    monkeypatch.setattr(StyleStructureService, "build_automatic_structure", record_build)

    started = client.post(
        "/api/v1/projects/external/style-analysis/external-sessions",
        json={
            "target": {
                "kind": "document",
                "document_id": document_id,
                "text_revision_id": text_revision_id,
            },
            "executor_model_id": "gpt-test",
            "rebuild_structure": True,
        },
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["data"]["session_id"]
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        row = connection.execute(
            "SELECT cursor_json, request_json FROM style_external_analysis_sessions "
            "WHERE id = ?",
            (session_id,),
        ).fetchone()
        assert row is not None
        cursor = json.loads(row[0])
        request = json.loads(row[1])
        assert request["rebuild_structure"] is True
        assert build_calls == [
            {
                "document_id": document_id,
                "text_revision_id": text_revision_id,
                "set_current": False,
            }
        ]
        assert cursor["engine_cursor"]["structure_revision_id"] == old_structure_id
    finally:
        connection.close()


def test_external_task_loop_reopens_and_reads_terminal_results(
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
    task_count = 0
    while snapshot["status"] == "active":
        task = snapshot["task"]
        assert task is not None
        task_count += 1
        submitted = client.post(
            f"{base}/external-sessions/{snapshot['session_id']}/tasks/"
            f"{task['task_id']}/submit",
            json={
                "expected_task_version": task["task_version"],
                "executor_model_id": "gpt-test",
                "response": _response_for_contract(task["response_contract_id"]),
            },
        )
        assert submitted.status_code == 200
        status = client.get(f"{base}/external-sessions/{snapshot['session_id']}")
        assert status.status_code == 200
        snapshot = status.json()["data"]
        assert task_count < 20

    assert task_count > 1
    assert snapshot["status"] in {"succeeded", "partial"}
    connection = sqlite3.connect(data_root / "external" / "story.db")
    try:
        structure_id = connection.execute(
            "SELECT current_structure_revision_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    semantics = client.get(
        f"{base}/documents/{document_id}/semantics",
        params={"structure_revision_id": structure_id},
    )
    metrics = client.get(
        f"{base}/documents/{document_id}/metrics",
        params={"structure_revision_id": structure_id},
    )
    assert semantics.status_code == 200
    assert metrics.status_code == 200
