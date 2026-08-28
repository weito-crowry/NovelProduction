from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_api.app import create_app
from novel_api.config import ApiSettings


def _client(data_root: Path, webui_dist: Path | None = None) -> TestClient:
    return TestClient(
        create_app(ApiSettings(data_root=data_root, webui_dist=webui_dist))
    )


def test_without_webui_dist_preserves_api_only_root_behavior(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/")

    assert response.status_code == 404
    assert response.text == '{"detail":"Not Found"}'


def test_valid_webui_dist_requires_index_and_serves_root(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>D1</html>", encoding="utf-8")

    with _client(tmp_path / "missing-data-root", dist) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text == "<html>D1</html>"
    assert response.headers["content-type"].startswith("text/html")


def test_frontend_deep_route_falls_back_to_index(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")

    with _client(tmp_path, dist) as client:
        response = client.get("/projects/A/dashboard")

    assert response.status_code == 200
    assert response.text == "<html>SPA</html>"


def test_existing_static_asset_is_served(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('D1')", encoding="utf-8")

    with _client(tmp_path, dist) as client:
        response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('D1')"


def test_static_get_and_head_serve_same_resource_without_head_body(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>HEAD</html>", encoding="utf-8")

    with _client(tmp_path, dist) as client:
        get_response = client.get("/projects/A/dashboard")
        head_response = client.head("/projects/A/dashboard")

    assert get_response.status_code == head_response.status_code == 200
    assert head_response.content == b""
    assert head_response.headers["content-length"] == str(len(get_response.content))


def test_api_health_has_precedence_over_spa_fallback(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")

    with _client(tmp_path, dist) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "v1"}


def test_unknown_api_route_keeps_structured_404_and_never_returns_spa(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>DO NOT SERVE</html>", encoding="utf-8")

    with _client(tmp_path, dist) as client:
        response = client.get("/api/v1/unknown")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested resource was not found.",
            "project_id": None,
            "details": {},
        }
    }
    assert "DO NOT SERVE" not in response.text


@pytest.mark.parametrize(
    ("dist_kind", "message"),
    [
        ("missing", "webui_dist does not exist"),
        ("file", "webui_dist must be a directory"),
        ("no-index", "webui_dist must contain index.html"),
    ],
)
def test_invalid_explicit_webui_dist_fails_at_app_creation(
    tmp_path: Path, dist_kind: str, message: str
) -> None:
    dist = tmp_path / "dist"
    if dist_kind == "file":
        dist.write_text("not a directory", encoding="utf-8")
    elif dist_kind == "no-index":
        dist.mkdir()

    with pytest.raises(ValueError, match=message):
        create_app(ApiSettings(data_root=tmp_path, webui_dist=dist))


def test_traversal_candidate_is_never_served_from_outside_dist(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET OUTSIDE DIST", encoding="utf-8")

    with _client(tmp_path, dist) as client:
        response = client.get("/nested/%2e%2e/outside.txt")

    assert "SECRET OUTSIDE DIST" not in response.text
    assert response.status_code in {404, 200}
    if response.status_code == 200:
        assert response.text == "<html>SPA</html>"


def test_static_app_creation_does_not_touch_database(
    tmp_path: Path, monkeypatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")

    def fail_if_database_is_touched(*args: object, **kwargs: object) -> None:
        raise AssertionError("static app creation must not open SQLite")

    monkeypatch.setattr("sqlite3.connect", fail_if_database_is_touched)

    app = create_app(
        ApiSettings(data_root=tmp_path / "uncreated-data", webui_dist=dist)
    )

    assert app.state.settings.webui_dist == dist
