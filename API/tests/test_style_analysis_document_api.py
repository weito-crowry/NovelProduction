from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator


def _create_reference_document(
    client: TestClient,
    data_root: Path,
    raw_text: str = "Episode 1\n\n本文。",
) -> tuple[int, int, int]:
    created = client.post(
        "/api/v1/projects",
        json={"project_id": "reference", "working_title": "Reference"},
    )
    assert created.status_code == 201
    imported = client.post(
        "/api/v1/projects/reference/style-analysis/imports/file",
        data={"source_type": "text"},
        files={"file": ("reference.txt", raw_text.encode(), "text/plain")},
    )
    assert imported.status_code == 201

    connection = sqlite3.connect(data_root / "reference" / "story.db")
    try:
        document_id, text_revision_id = connection.execute(
            "SELECT id, current_text_revision_id FROM style_documents "
            "WHERE reference_episode_id IS NOT NULL"
        ).fetchone()
        result = DocumentAnalysisOrchestrator(
            connection, model_client=None
        ).analyze_document(
            document_id=document_id,
            text_revision_id=text_revision_id,
            preset="deterministic",
        )
        connection.commit()
        assert result.structure_revision_id is not None
        return (
            int(document_id),
            int(text_revision_id),
            int(result.structure_revision_id),
        )
    finally:
        connection.close()


def test_canonical_document_revision_and_content_routes(
    client: TestClient, data_root: Path
) -> None:
    document_id, text_revision_id, structure_revision_id = _create_reference_document(
        client, data_root
    )
    base = "/api/v1/projects/reference/style-analysis"

    documents = client.get(f"{base}/documents")
    assert documents.status_code == 200
    assert documents.json()["data"] == [
        {
            "document_id": document_id,
            "kind": "reference_episode",
            "current_text_revision_id": text_revision_id,
            "current_structure_revision_id": structure_revision_id,
            "current_structure_kind": "automatic",
            "analysis_status": {
                "basic": {"state": "current", "reasons": []},
                "semantic": {"state": "not_analyzed", "reasons": []},
            },
        }
    ]

    document = client.get(f"{base}/documents/{document_id}")
    assert document.status_code == 200
    assert document.json()["data"] == documents.json()["data"][0]

    revisions = client.get(f"{base}/documents/{document_id}/revisions")
    assert revisions.status_code == 200
    assert revisions.json()["data"][0]["id"] == text_revision_id
    assert revisions.json()["data"][0]["revision_no"] == 1

    text = client.get(
        f"{base}/documents/{document_id}/text",
        params={"text_revision_id": text_revision_id},
    )
    assert text.status_code == 200
    assert text.json()["data"]["canonical_text"] == "Episode 1\n\n本文。"

    structures = client.get(f"{base}/documents/{document_id}/structures")
    assert structures.status_code == 200
    assert structures.json()["data"][0]["id"] == structure_revision_id
    assert structures.json()["data"][0]["source_kind"] == "automatic"

    structure = client.get(
        f"{base}/documents/{document_id}/structure",
        params={"structure_revision_id": structure_revision_id},
    )
    assert structure.status_code == 200
    structure_data = structure.json()["data"]
    assert structure_data["id"] == structure_revision_id
    assert structure_data["scenes"]
    assert structure_data["blocks"]
    assert structure_data["sentences"]
    assert structure_data["blocks"][0]["text"]

    metrics = client.get(
        f"{base}/documents/{document_id}/metrics",
        params={"structure_revision_id": structure_revision_id},
    )
    assert metrics.status_code == 200
    metrics_data = metrics.json()["data"]
    assert metrics_data["structure_revision_id"] == structure_revision_id
    assert metrics_data["analysis_run_ids"]
    assert any(
        item["metric_name"] == "text.char_count"
        for item in metrics_data["measurements"]
    )

    selected = client.post(
        f"{base}/documents/{document_id}/structures/{structure_revision_id}/select-current"
    )
    assert selected.status_code == 200
    assert (
        selected.json()["data"]["current_structure_revision_id"]
        == structure_revision_id
    )


def test_manual_structure_split_and_merge_routes_create_current_revisions(
    client: TestClient, data_root: Path
) -> None:
    document_id, _, structure_revision_id = _create_reference_document(
        client,
        data_root,
        raw_text="第一文。\n\n第二文。\n\n第三文。",
    )
    base = "/api/v1/projects/reference/style-analysis"
    structure = client.get(
        f"{base}/documents/{document_id}/structure",
        params={"structure_revision_id": structure_revision_id},
    ).json()["data"]
    scene_id = structure["scenes"][0]["id"]
    after_block_id = structure["blocks"][0]["id"]

    split = client.post(
        f"{base}/documents/{document_id}/scenes/{scene_id}/split",
        json={
            "after_block_id": after_block_id,
            "expected_structure_revision_id": structure_revision_id,
        },
    )
    assert split.status_code == 200
    split_data = split.json()["data"]
    assert split_data["source_kind"] == "manual"
    assert split_data["parent_structure_revision_id"] == structure_revision_id
    assert split_data["scene_count"] == 2

    split_scenes = split_data["scenes"]
    merged = client.post(
        f"{base}/documents/{document_id}/scenes/merge",
        json={
            "scene_id": split_scenes[0]["id"],
            "next_scene_id": split_scenes[1]["id"],
            "expected_structure_revision_id": split_data["id"],
        },
    )
    assert merged.status_code == 200
    merged_data = merged.json()["data"]
    assert merged_data["source_kind"] == "manual"
    assert merged_data["parent_structure_revision_id"] == split_data["id"]
    assert merged_data["scene_count"] == 1

    current = client.get(f"{base}/documents/{document_id}").json()["data"]
    assert current["current_structure_revision_id"] == merged_data["id"]
