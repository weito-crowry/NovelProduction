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


def fingerprint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def test_d3_browse_endpoints_return_project_envelopes_and_page_in_order(
    client: TestClient,
) -> None:
    base = create_project(client, "d3-browse")
    for index in range(3):
        data(
            client.post(
                f"{base}/world-facts",
                json={"statement": f"fact {index}", "title": f"fact {index}"},
            ),
            "d3-browse",
        )
        data(
            client.post(
                f"{base}/characters", json={"display_name": f"character {index}"}
            ),
            "d3-browse",
        )
        data(
            client.post(
                f"{base}/timeline/events",
                json={"title": f"event {index}", "event_date": f"2104-0{index + 1}-01"},
            ),
            "d3-browse",
        )
    events = data(
        client.get(f"{base}/timeline/events", params={"limit": 2, "offset": 1}),
        "d3-browse",
    )
    facts = data(
        client.get(f"{base}/world-facts", params={"limit": 2, "offset": 1}),
        "d3-browse",
    )
    characters = data(
        client.get(f"{base}/characters", params={"limit": 2, "offset": 1}),
        "d3-browse",
    )
    first_event = data(
        client.post(
            f"{base}/timeline/events",
            json={"title": "relation source", "event_date": "2105-01-01"},
        ),
        "d3-browse",
    )
    second_event = data(
        client.post(
            f"{base}/timeline/events",
            json={"title": "relation target", "event_date": "2105-02-01"},
        ),
        "d3-browse",
    )
    relation = data(
        client.post(
            f"{base}/timeline/relations",
            json={
                "source_id": first_event["id"],
                "target_id": second_event["id"],
                "relation_type": "causes",
            },
        ),
        "d3-browse",
    )
    relations = data(
        client.get(
            f"{base}/timeline/relations",
            params={"event_id": first_event["id"], "limit": 50, "offset": 0},
        ),
        "d3-browse",
    )

    assert [item["id"] for item in facts] == [2, 3]
    assert [item["id"] for item in characters] == [2, 3]
    assert [item["title"] for item in events] == ["event 1", "event 2"]
    assert relations == [relation]


def test_d3_browse_endpoints_are_project_isolated_and_missing_project_is_normalized(
    client: TestClient,
) -> None:
    base_a = create_project(client, "d3-a")
    base_b = create_project(client, "d3-b")
    fact = data(
        client.post(f"{base_a}/world-facts", json={"statement": "A only"}), "d3-a"
    )
    character = data(
        client.post(f"{base_a}/characters", json={"display_name": "A only"}), "d3-a"
    )
    event = data(
        client.post(f"{base_a}/timeline/events", json={"title": "A only"}), "d3-a"
    )
    for path in ("/world-facts", "/characters", "/timeline/events"):
        assert data(client.get(f"{base_b}{path}"), "d3-b") == []
    for path in (
        f"/world-facts/{fact['id']}",
        f"/characters/{character['id']}",
        f"/timeline/events/{event['id']}",
    ):
        assert client.get(f"{base_b}{path}").status_code == 404
    missing = client.get("/api/v1/projects/not-created/world-facts")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/world-facts", {"limit": 0}),
        ("/world-facts", {"limit": 101}),
        ("/characters", {"offset": -1}),
        ("/timeline/events", {"limit": 0}),
        ("/timeline/relations", {"event_id": 0}),
        ("/timeline/relations", {"event_id": -1}),
    ],
)
def test_d3_browse_query_validation_returns_422(
    client: TestClient, path: str, params: dict[str, int]
) -> None:
    base = create_project(client, "d3-validation")
    response = client.get(f"{base}{path}", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_d3_browse_gets_use_read_only_connection_without_db_changes(
    client: TestClient,
    data_root: Path,
) -> None:
    base = create_project(client, "d3-read-only")
    data(client.post(f"{base}/world-facts", json={"statement": "read"}), "d3-read-only")
    db_path = data_root / "d3-read-only" / "story.db"
    before = fingerprint(db_path)
    responses = (
        client.get(f"{base}/world-facts"),
        client.get(f"{base}/characters"),
        client.get(f"{base}/timeline/events"),
        client.get(f"{base}/timeline/relations"),
    )
    assert all(response.status_code == 200 for response in responses)
    assert fingerprint(db_path) == before
