from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from novel_core.errors import DocumentStorageError
from novel_core.services.draft_service import DraftService


def _data(response: Any, project_id: str = "phase-e") -> Any:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def _create_episode(
    client: TestClient, project_id: str = "phase-e"
) -> tuple[str, dict[str, Any]]:
    base = f"/api/v1/projects/{project_id}"
    created = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": "Phase E"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["project_id"] == project_id
    chapter = _data(client.post(f"{base}/chapters", json={"title": "章"}), project_id)
    episode = _data(
        client.post(
            f"{base}/chapters/{chapter['id']}/episodes",
            json={"title": "対象話"},
        ),
        project_id,
    )
    return base, episode


def test_draft_get_formats_and_repeated_annotation_keys(client: TestClient) -> None:
    base, episode = _create_episode(client)
    save = _data(
        client.post(
            f"{base}/episodes/{episode['id']}/drafts",
            json={
                "html": (
                    '<p id="corr" data-np-type="dialogue" '
                    'data-ann-emotions="[&quot;焦り&quot;]" '
                    'data-ann-mood="tense">本文</p>'
                    '<p data-np-type="note">制作メモ</p>'
                )
            },
        )
    )

    default_html = _data(client.get(f"{base}/episodes/{episode['id']}/draft"))
    assert default_html["format"] == "html"
    assert "data-ann-" not in default_html["content"]
    assert "制作メモ" in default_html["content"]

    selected = _data(
        client.get(
            f"{base}/episodes/{episode['id']}/draft",
            params=[
                ("annotation_projection", "selected"),
                ("annotation_keys", "emotions"),
                ("annotation_keys", "mood"),
            ],
        )
    )
    assert 'data-ann-emotions="[&quot;焦り&quot;]"' in selected["content"]
    assert 'data-ann-mood="tense"' in selected["content"]
    assert "制作メモ" in selected["content"]

    all_annotations = _data(
        client.get(
            f"{base}/episodes/{episode['id']}/draft",
            params={"annotation_projection": "all"},
        )
    )
    assert "data-ann-emotions" in all_annotations["content"]
    assert "data-ann-mood" in all_annotations["content"]

    web = _data(
        client.get(f"{base}/episodes/{episode['id']}/draft", params={"format": "web"})
    )
    assert web["format"] == "web"
    assert 'id="' in web["content"]
    assert "制作メモ" not in web["content"]
    assert "data-ann-" not in web["content"]
    web_with_notes = _data(
        client.get(
            f"{base}/episodes/{episode['id']}/draft",
            params={"format": "web", "include_notes": "true"},
        )
    )
    assert "制作メモ" in web_with_notes["content"]

    document = _data(
        client.get(
            f"{base}/episodes/{episode['id']}/draft", params={"format": "document"}
        )
    )
    assert document["format"] == "document"
    assert isinstance(document["content"], dict)
    assert document["content"]["schema_version"] == 1
    assert document["content"]["blocks"][0]["attrs"] == {}
    assert document["content"]["blocks"][0]["annotations"] == {
        "emotions": ["焦り"],
        "mood": "tense",
    }
    assert save["id_map"]["corr"].startswith("blk_")


@pytest.mark.parametrize(
    "params",
    [
        {"annotation_projection": "selected"},
        {"annotation_projection": "all", "annotation_keys": "emotions"},
        {"annotation_projection": "none", "annotation_keys": "emotions"},
        {"format": "html", "include_notes": "true"},
        {"format": "web", "annotation_projection": "selected"},
        {"format": "document", "include_notes": "true"},
        {"format": "unknown"},
    ],
)
def test_draft_get_rejects_irrelevant_query_combinations(
    client: TestClient, params: dict[str, str]
) -> None:
    base, episode = _create_episode(client)

    response = client.get(f"{base}/episodes/{episode['id']}/draft", params=params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_draft_save_rejects_html_set_and_metadata_remove_conflict(
    client: TestClient,
) -> None:
    base, episode = _create_episode(client)

    response = client.post(
        f"{base}/episodes/{episode['id']}/drafts",
        json={
            "html": '<p id="block" data-ann-foo="html">本文</p>',
            "metadata_updates": {
                "block": {"remove_annotations": ["foo"]},
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    latest = client.get(f"{base}/episodes/{episode['id']}/draft")
    assert latest.status_code == 200
    assert latest.json()["data"] is None


def test_draft_save_accepts_empty_sources_and_preserves_metadata_presence(
    client: TestClient,
) -> None:
    base, empty_plain_episode = _create_episode(client)
    empty_plain = _data(
        client.post(
            f"{base}/episodes/{empty_plain_episode['id']}/drafts",
            json={"plain_text": ""},
        )
    )
    assert empty_plain["revision"] == 1

    empty_html_base, empty_html_episode = _create_episode(client, "phase-e-empty-html")
    empty_html = _data(
        client.post(
            f"{empty_html_base}/episodes/{empty_html_episode['id']}/drafts",
            json={"html": ""},
        ),
        "phase-e-empty-html",
    )
    assert empty_html["revision"] == 1

    first = _data(
        client.post(
            f"{base}/episodes/{empty_plain_episode['id']}/drafts",
            json={
                "html": '<p id="block">本文</p>',
                "expected_parent_draft_id": empty_plain["id"],
            },
        )
    )
    formal_id = first["id_map"]["block"]
    second = _data(
        client.post(
            f"{base}/episodes/{empty_plain_episode['id']}/drafts",
            json={
                "html": None,
                "metadata_updates": {
                    formal_id: {
                        "attrs": {"scene_id": None},
                        "annotations": {"nullable": None},
                    }
                },
                "expected_parent_draft_id": first["id"],
            },
        )
    )
    assert second["revision"] == 3
    document = _data(
        client.get(
            f"{base}/episodes/{empty_plain_episode['id']}/draft",
            params={"format": "document"},
        )
    )
    assert document["content"]["blocks"][0]["attrs"] == {}
    assert document["content"]["blocks"][0]["annotations"] == {"nullable": None}

    invalid_patch = client.post(
        f"{base}/episodes/{empty_plain_episode['id']}/drafts",
        json={
            "metadata_updates": {formal_id: {}},
            "expected_parent_draft_id": second["id"],
        },
    )
    assert invalid_patch.status_code == 400
    assert invalid_patch.json()["error"]["code"] == "VALIDATION_ERROR"


def test_draft_save_maps_document_schema_and_storage_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, episode = _create_episode(client)
    malformed = client.post(
        f"{base}/episodes/{episode['id']}/drafts",
        json={"html": "<div>not authoring html</div>"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "DOCUMENT_SCHEMA_ERROR"

    def broken_get(self: DraftService, episode_id: int, revision: int | None = None):
        raise DocumentStorageError()

    monkeypatch.setattr(DraftService, "get_draft", broken_get)
    storage_error = client.get(f"{base}/episodes/{episode['id']}/draft")
    assert storage_error.status_code == 500
    assert storage_error.json()["error"]["code"] == "DOCUMENT_STORAGE_ERROR"


def test_draft_export_uses_canonical_exporter_and_absence_convention(
    client: TestClient,
) -> None:
    base, episode = _create_episode(client)
    absent = client.get(f"{base}/episodes/{episode['id']}/draft/export")
    assert _data(absent) is None

    _data(
        client.post(
            f"{base}/episodes/{episode['id']}/drafts",
            json={"html": '<p>本文<br>続き</p><p data-np-type="note">メモ</p>'},
        )
    )
    exported = _data(client.get(f"{base}/episodes/{episode['id']}/draft/export"))
    assert exported == {
        "format": "narou",
        "media_type": "text/plain",
        "content": "本文\n続き",
        "suggested_filename": f"episode-{episode['id']}-r1.txt",
        "warnings": [],
    }
