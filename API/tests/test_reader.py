from __future__ import annotations

import re
from typing import Any

from fastapi.testclient import TestClient


def _data(response: Any, project_id: str = "reader-project") -> Any:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    return payload["data"]


def _create_reader_project(client: TestClient) -> dict[str, int]:
    project_id = "reader-project"
    created = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": '作品 <& "タイトル">'},
    )
    assert created.status_code == 201, created.text
    base = f"/api/v1/projects/{project_id}"

    chapter_one = _data(client.post(f"{base}/chapters", json={"title": "章 <&"}))
    first = _data(
        client.post(
            f"{base}/chapters/{chapter_one['id']}/episodes",
            json={"title": '話1 "第一"'},
        )
    )
    second = _data(
        client.post(
            f"{base}/chapters/{chapter_one['id']}/episodes",
            json={"title": "話2（本文なし）"},
        )
    )
    chapter_two = _data(client.post(f"{base}/chapters", json={"title": "第二章"}))
    third = _data(
        client.post(
            f"{base}/chapters/{chapter_two['id']}/episodes",
            json={"title": "話3"},
        )
    )
    fourth = _data(
        client.post(
            f"{base}/chapters/{chapter_two['id']}/episodes",
            json={"title": "話4"},
        )
    )
    for episode, body in (
        (first, {"html": "<p>本文1</p>"}),
        (third, {"html": "<p>本文3</p>"}),
        (fourth, {"html": '<p>本文4</p><p data-np-type="note">制作メモ</p>'}),
    ):
        saved = client.post(f"{base}/episodes/{episode['id']}/drafts", json=body)
        assert saved.status_code == 201, saved.text

    return {
        "first": first["id"],
        "second": second["id"],
        "third": third["id"],
        "fourth": fourth["id"],
    }


def test_reader_toc_is_server_html_and_preserves_narrative_order(
    client: TestClient,
) -> None:
    episode_ids = _create_reader_project(client)

    response = client.get("/read/projects/reader-project/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html; charset=utf-8")
    assert '<html lang="ja">' in response.text
    assert "作品 &lt;&amp; &quot;タイトル&quot;&gt;" in response.text
    assert "章 &lt;&amp;" in response.text
    assert response.text.index("話1") < response.text.index("話2（本文なし）")
    assert response.text.index("話2（本文なし）") < response.text.index("話3")
    assert response.text.index("話3") < response.text.index("話4")
    assert (
        f"/read/projects/reader-project/episodes/{episode_ids['first']}/"
        in response.text
    )
    assert (
        f"/read/projects/reader-project/episodes/{episode_ids['third']}/"
        in response.text
    )
    assert (
        f"/read/projects/reader-project/episodes/{episode_ids['fourth']}/"
        in response.text
    )
    assert (
        f"/read/projects/reader-project/episodes/{episode_ids['second']}/"
        not in response.text
    )
    assert "本文未作成" in response.text
    assert "<script" not in response.text.lower()


def test_reader_catalog_uses_metadata_and_only_loads_current_episode_document(
    client: TestClient, monkeypatch
) -> None:
    from novel_core.services.draft_service import DraftService

    episode_ids = _create_reader_project(client)
    calls: list[int] = []
    original = DraftService.get_draft

    def tracked_get_draft(self, episode_id: int, revision: int | None = None):
        calls.append(episode_id)
        return original(self, episode_id, revision)

    monkeypatch.setattr(DraftService, "get_draft", tracked_get_draft)

    toc = client.get("/read/projects/reader-project/")
    episode = client.get(
        f"/read/projects/reader-project/episodes/{episode_ids['third']}/"
    )

    assert toc.status_code == 200
    assert calls == [episode_ids["third"]]
    assert episode.status_code == 200
    assert "本文3" in episode.text


def test_reader_routes_are_excluded_from_openapi_schema(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert not any(path.startswith("/read/") for path in paths)


def test_reader_route_precedes_spa_fallback(data_root, tmp_path) -> None:
    from novel_api.app import create_app
    from novel_api.config import ApiSettings

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    with TestClient(
        create_app(ApiSettings(data_root=data_root, webui_dist=dist))
    ) as client:
        response = client.get("/read/projects/missing/")

    assert response.status_code == 404
    assert response.text != "<html>SPA</html>"


def test_reader_episode_uses_rendered_body_and_cross_chapter_draft_navigation(
    client: TestClient,
) -> None:
    episode_ids = _create_reader_project(client)

    first = client.get(
        f"/read/projects/reader-project/episodes/{episode_ids['first']}/"
    )
    third = client.get(
        f"/read/projects/reader-project/episodes/{episode_ids['third']}/"
    )
    fourth = client.get(
        f"/read/projects/reader-project/episodes/{episode_ids['fourth']}/"
    )

    assert first.status_code == third.status_code == fourth.status_code == 200
    assert '<h1 id="reader-title">話1 &quot;第一&quot;</h1>' in first.text
    assert first.text.count('<article id="novel-body">') == 1
    assert "本文1" in first.text
    assert "制作メモ" not in fourth.text
    assert 'data-np-type="note"' not in fourth.text
    assert "data-ann-" not in fourth.text
    assert first.text.count('aria-label="Episode navigation"') == 2
    assert first.text.count('id="reader-title"') == 1
    assert first.text.count('id="reader-chapter-title"') == 1
    assert first.text.count('id="reader-contents"') == 1
    assert first.text.count('rel="contents"') == 1
    assert first.text.count('rel="prev"') == 0
    third_href = f"/read/projects/reader-project/episodes/{episode_ids['third']}/"
    assert first.text.count(f'href="{third_href}"') == 2
    assert "1 / 3" in first.text
    first_href = f"/read/projects/reader-project/episodes/{episode_ids['first']}/"
    contents_href = "/read/projects/reader-project/"
    assert third.text.count('id="reader-title"') == 1
    assert third.text.count('id="reader-chapter-title"') == 1
    assert third.text.count('id="reader-contents"') == 1
    assert third.text.count('id="reader-prev"') == 1
    assert third.text.count('id="reader-next"') == 1
    assert third.text.count('rel="prev"') == 1
    assert third.text.count('rel="contents"') == 1
    assert third.text.count('rel="next"') == 1
    assert third.text.count('aria-label="Episode navigation"') == 2
    assert third.text.count(f'href="{first_href}"') == 2
    assert third.text.count(f'href="{contents_href}"') == 2
    fourth_href = f"/read/projects/reader-project/episodes/{episode_ids['fourth']}/"
    assert third.text.count(f'href="{fourth_href}"') == 2
    navigation = re.findall(
        r'<nav class="reader-navigation" aria-label="Episode navigation">'
        r"(.*?)</nav>",
        third.text,
    )
    assert len(navigation) == 2
    assert 'id="reader-prev"' in navigation[0]
    assert 'rel="prev"' in navigation[0]
    assert 'id="reader-next"' in navigation[0]
    assert 'rel="next"' in navigation[0]
    assert 'id="reader-' not in navigation[1]
    assert " rel=" not in navigation[1]
    assert "2 / 3" in third.text
    third_prev_href = f"/read/projects/reader-project/episodes/{episode_ids['third']}/"
    assert fourth.text.count('id="reader-title"') == 1
    assert fourth.text.count('id="reader-chapter-title"') == 1
    assert fourth.text.count('id="reader-contents"') == 1
    assert fourth.text.count('id="reader-prev"') == 1
    assert fourth.text.count('rel="prev"') == 1
    assert fourth.text.count(f'href="{third_prev_href}"') == 2
    assert fourth.text.count('rel="next"') == 0
    assert fourth.text.count('id="reader-next"') == 0
    assert "3 / 3" in fourth.text
    assert "<script" not in first.text.lower()


def test_reader_episode_returns_not_found_without_draft_or_for_unknown_episode(
    client: TestClient,
) -> None:
    episode_ids = _create_reader_project(client)

    no_draft = client.get(
        f"/read/projects/reader-project/episodes/{episode_ids['second']}/"
    )
    unknown = client.get("/read/projects/reader-project/episodes/999999/")
    missing_project = client.get("/read/projects/missing/episodes/1/")

    assert no_draft.status_code == 404
    assert unknown.status_code == 404
    assert missing_project.status_code == 404
