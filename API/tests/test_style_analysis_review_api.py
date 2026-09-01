from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def _create_project(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": "reference", "working_title": "Reference"},
    )
    assert response.status_code == 201


def _import_reference(client: TestClient) -> int:
    response = client.post(
        "/api/v1/projects/reference/style-analysis/imports/file",
        data={"source_type": "text"},
        files={
            "file": ("reference.txt", io.BytesIO(b"Episode 1\n\nText"), "text/plain")
        },
    )
    assert response.status_code == 201
    return int(response.json()["data"]["reference_work_id"])


def test_style_review_and_manual_identity_routes_are_separate(
    client: TestClient, data_root: Path
) -> None:
    _create_project(client)
    work_id = _import_reference(client)

    entity_response = client.post(
        "/api/v1/projects/reference/style-analysis/entities",
        json={
            "reference_work_id": work_id,
            "entity_type": "person",
            "canonical_name": "人物",
        },
    )
    assert entity_response.status_code == 201
    entity = entity_response.json()["data"]
    assert entity["origin"] == "manual"
    entity_id = entity["id"]

    alias_response = client.post(
        f"/api/v1/projects/reference/style-analysis/entities/{entity_id}/aliases",
        json={"alias": " 別名 ", "alias_kind": "name"},
    )
    assert alias_response.status_code == 201
    assert alias_response.json()["data"]["alias"] == "別名"

    item_response = client.post(
        "/api/v1/projects/reference/style-analysis/review-items",
        json={"subject_type": "entity", "subject_id": entity_id, "priority": "high"},
    )
    assert item_response.status_code == 201
    item = item_response.json()["data"]
    assert item["item_type"] == "manual_review"
    assert item["reason_code"] == "user_marked"
    assert item["status"] == "open"
    assert item["version"] == 1

    conflict = client.post(
        f"/api/v1/projects/reference/style-analysis/review-items/{item['id']}/resolve",
        json={"expected_version": 2, "note": "競合"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"

    resolved = client.post(
        f"/api/v1/projects/reference/style-analysis/review-items/{item['id']}/resolve",
        json={"expected_version": 1},
    )
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "resolved"

    override = client.post(
        "/api/v1/projects/reference/style-analysis/overrides",
        json={
            "subject_type": "entity",
            "subject_id": entity_id,
            "field_path": "entity.canonical_name",
            "operation": "set",
            "value": "変更人物",
            "reference_work_id": work_id,
        },
    )
    assert override.status_code == 201
    assert override.json()["data"]["operation"] == "set"
    assert override.json()["data"]["correction_class"] == "semantic_reanalysis_required"

    connection = sqlite3.connect(data_root / "reference" / "story.db")
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM style_review_items WHERE status='resolved'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM style_manual_overrides"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_metric_only_override_enqueues_internal_metrics_job_after_commit(
    client: TestClient, data_root: Path
) -> None:
    _create_project(client)
    work_id = _import_reference(client)
    term_response = client.post(
        "/api/v1/projects/reference/style-analysis/terms",
        json={
            "reference_work_id": work_id,
            "canonical_label": "用語",
            "term_type": "other",
        },
    )
    assert term_response.status_code == 201
    term_id = term_response.json()["data"]["id"]
    response = client.post(
        "/api/v1/projects/reference/style-analysis/overrides",
        json={
            "subject_type": "term",
            "subject_id": term_id,
            "field_path": "term.novelty",
            "operation": "set",
            "value": "work_specific",
            "reference_work_id": work_id,
        },
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["correction_class"] == "metric_only_recompute"
    assert data["job_id"] is not None
    connection = sqlite3.connect(data_root / "reference" / "story.db")
    try:
        job = connection.execute(
            "SELECT job_type, payload_json FROM style_jobs WHERE id=?",
            (data["job_id"],),
        ).fetchone()
        assert job[0] == "analyze_reference_work"
        assert '"preset":"metrics"' in job[1]
    finally:
        connection.close()


def test_generic_review_confirm_and_reject_routes_do_not_exist(
    client: TestClient,
) -> None:
    _create_project(client)
    response = client.post(
        "/api/v1/projects/reference/style-analysis/review-items/1/confirm"
    )
    assert response.status_code == 404
