from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def data(response: Any, project_id: str) -> Any:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def create_project(client: TestClient, project_id: str) -> str:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": project_id},
    )
    assert response.status_code == 201, response.text
    return f"/api/v1/projects/{project_id}"


def create_episode(client: TestClient, base: str, title: str = "Episode") -> dict:
    chapter = data(
        client.post(f"{base}/chapters", json={"title": "Chapter"}),
        base.rsplit("/", 1)[-1],
    )
    return data(
        client.post(f"{base}/chapters/{chapter['id']}/episodes", json={"title": title}),
        base.rsplit("/", 1)[-1],
    )


def fingerprint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def test_information_list_is_ordered_paged_and_project_scoped(
    client: TestClient,
) -> None:
    base_a = create_project(client, "d4-information-a")
    base_b = create_project(client, "d4-information-b")
    for index in range(3):
        data(
            client.post(f"{base_a}/information", json={"statement": f"A {index}"}),
            "d4-information-a",
        )
    assert [
        item["id"]
        for item in data(
            client.get(f"{base_a}/information", params={"limit": 2, "offset": 1}),
            "d4-information-a",
        )
    ] == [2, 3]
    assert data(client.get(f"{base_b}/information"), "d4-information-b") == []


@pytest.mark.parametrize(
    "params",
    ({"limit": 0}, {"limit": 101}, {"offset": -1}),
)
def test_information_list_validates_paging(
    client: TestClient, params: dict[str, int]
) -> None:
    base = create_project(client, "d4-information-validation")
    response = client.get(f"{base}/information", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_canon_decision_list_is_ordered_paged_and_project_scoped(
    client: TestClient,
) -> None:
    base_a = create_project(client, "d4-canon-a")
    base_b = create_project(client, "d4-canon-b")
    items = [
        data(
            client.post(f"{base_a}/information", json={"statement": f"A {index}"}),
            "d4-canon-a",
        )
        for index in range(3)
    ]
    for item in items:
        response = client.post(
            f"{base_a}/canon/status",
            json={
                "entity_type": "information_item",
                "entity_id": item["id"],
                "target_status": "canon",
                "expected_version": item["version"],
                "reason": "approved",
            },
        )
        assert response.status_code == 200, response.text
    decisions = data(
        client.get(f"{base_a}/canon/decisions", params={"limit": 2, "offset": 1}),
        "d4-canon-a",
    )
    assert [decision["id"] for decision in decisions] == [2, 3]
    assert data(client.get(f"{base_b}/canon/decisions"), "d4-canon-b") == []


@pytest.mark.parametrize(
    "params",
    ({"limit": 0}, {"limit": 101}, {"offset": -1}),
)
def test_canon_decision_list_validates_paging(
    client: TestClient, params: dict[str, int]
) -> None:
    base = create_project(client, "d4-canon-validation")
    response = client.get(f"{base}/canon/decisions", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reader_disclosure_get_returns_record_or_null_and_is_read_only(
    client: TestClient,
    data_root: Path,
) -> None:
    base = create_project(client, "d4-disclosure")
    item = data(
        client.post(f"{base}/information", json={"statement": "Secret"}),
        "d4-disclosure",
    )
    episode = create_episode(client, base)
    db_path = data_root / "d4-disclosure" / "story.db"
    before = fingerprint(db_path)

    assert (
        data(
            client.get(f"{base}/information/{item['id']}/reader-disclosure"),
            "d4-disclosure",
        )
        is None
    )
    expected = data(
        client.put(
            f"{base}/information/{item['id']}/reader-disclosure",
            json={"episode_id": episode["id"]},
        ),
        "d4-disclosure",
    )
    assert (
        data(
            client.get(f"{base}/information/{item['id']}/reader-disclosure"),
            "d4-disclosure",
        )
        == expected
    )
    assert fingerprint(db_path) != before
    after_write = fingerprint(db_path)
    assert (
        client.get(f"{base}/information/{item['id']}/reader-disclosure").status_code
        == 200
    )
    assert fingerprint(db_path) == after_write


def test_reader_disclosure_get_rejects_missing_information(client: TestClient) -> None:
    base = create_project(client, "d4-disclosure-missing")
    response = client.get(f"{base}/information/999/reader-disclosure")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_exact_knowledge_get_returns_note_version_and_not_prior_effective_event(
    client: TestClient,
) -> None:
    base = create_project(client, "d4-knowledge")
    character = data(
        client.post(f"{base}/characters", json={"display_name": "Character"}),
        "d4-knowledge",
    )
    item = data(
        client.post(f"{base}/information", json={"statement": "Secret"}),
        "d4-knowledge",
    )
    chapter = data(
        client.post(f"{base}/chapters", json={"title": "Chapter"}), "d4-knowledge"
    )
    first = data(
        client.post(
            f"{base}/chapters/{chapter['id']}/episodes", json={"title": "First"}
        ),
        "d4-knowledge",
    )
    second = data(
        client.post(
            f"{base}/chapters/{chapter['id']}/episodes", json={"title": "Second"}
        ),
        "d4-knowledge",
    )
    prior = data(
        client.put(
            f"{base}/characters/{character['id']}/knowledge/{item['id']}",
            json={
                "episode_id": first["id"],
                "knowledge_state": "believes",
                "note": "prior",
            },
        ),
        "d4-knowledge",
    )
    assert (
        data(
            client.get(
                f"{base}/characters/{character['id']}/knowledge/{item['id']}",
                params={"episode_id": second["id"]},
            ),
            "d4-knowledge",
        )
        is None
    )
    effective = data(
        client.get(
            f"{base}/characters/{character['id']}/knowledge",
            params={"episode_id": second["id"]},
        ),
        "d4-knowledge",
    )
    assert effective[0]["event_id"] == prior["id"]

    exact = data(
        client.put(
            f"{base}/characters/{character['id']}/knowledge/{item['id']}",
            json={
                "episode_id": second["id"],
                "knowledge_state": "knows",
                "note": "exact",
            },
        ),
        "d4-knowledge",
    )
    assert (
        data(
            client.get(
                f"{base}/characters/{character['id']}/knowledge/{item['id']}",
                params={"episode_id": second["id"]},
            ),
            "d4-knowledge",
        )
        == exact
    )


def test_exact_knowledge_get_rejects_cross_project_ids(client: TestClient) -> None:
    base_a = create_project(client, "d4-knowledge-a")
    base_b = create_project(client, "d4-knowledge-b")
    character = data(
        client.post(f"{base_a}/characters", json={"display_name": "A"}),
        "d4-knowledge-a",
    )
    item = data(
        client.post(f"{base_a}/information", json={"statement": "A"}),
        "d4-knowledge-a",
    )
    episode = create_episode(client, base_a)
    response = client.get(
        f"{base_b}/characters/{character['id']}/knowledge/{item['id']}",
        params={"episode_id": episode["id"]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
