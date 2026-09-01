from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path
from threading import Barrier, Thread
from typing import Any

import pytest
from fastapi.testclient import TestClient

from novel_api.service_container import ProjectDescriptor, ProjectTarget
from novel_api.style_analysis.adapters.base import ImportedEpisode, ImportedWork
from novel_api.style_analysis.adapters.text import TextSourceAdapter
from novel_api.style_analysis.ingestion_service import import_source


def _create_project(client: TestClient, project_id: str) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"project_id": project_id, "working_title": project_id},
    )
    assert response.status_code == 201


def _data(response: Any) -> Any:
    payload = response.json()
    assert payload["project_id"] == "reference"
    return payload["data"]


def _upload(
    client: TestClient,
    *,
    source_type: str,
    filename: str,
    payload: bytes,
    media_type: str = "application/octet-stream",
) -> Any:
    return client.post(
        "/api/v1/projects/reference/style-analysis/imports/file",
        data={"source_type": source_type},
        files={"file": (filename, payload, media_type)},
    )


def _epub_payload() -> bytes:
    files = {
        "META-INF/container.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>'
        ),
        "OPS/content.opf": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>EPUB Work</dc:title><dc:creator>Writer</dc:creator></metadata>"
            '<manifest><item id="one" href="one.xhtml" '
            'media-type="application/xhtml+xml"/>'
            '<item id="two" href="two.xhtml" '
            'media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="one"/><itemref idref="two"/></spine></package>'
        ),
        "OPS/one.xhtml": "<html><body><h1>First</h1><p>本文一</p></body></html>",
        "OPS/two.xhtml": "<html><body><p>本文二</p></body></html>",
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return stream.getvalue()


def test_text_import_duplicate_catalog_and_no_job_row(
    client: TestClient, data_root: Path
) -> None:
    _create_project(client, "reference")
    payload = "第一話\n本文".encode()

    first = _upload(
        client,
        source_type="text",
        filename="book.txt",
        payload=payload,
        media_type="text/plain",
    )
    assert first.status_code == 201
    first_data = _data(first)
    assert first_data["reused_existing"] is False

    def fail_if_parsed(self: TextSourceAdapter, request: Any) -> Any:
        raise AssertionError("duplicate source was parsed")

    original = TextSourceAdapter.import_work
    TextSourceAdapter.import_work = fail_if_parsed
    try:
        duplicate = _upload(
            client,
            source_type="text",
            filename="renamed.txt",
            payload=payload,
            media_type="text/plain",
        )
    finally:
        TextSourceAdapter.import_work = original

    assert duplicate.status_code == 200
    duplicate_data = _data(duplicate)
    assert duplicate_data["reused_existing"] is True
    assert duplicate_data["reference_work_id"] == first_data["reference_work_id"]
    connection = sqlite3.connect(data_root / "reference" / "story.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM style_sources").fetchone() == (
            1,
        )
        assert connection.execute("SELECT COUNT(*) FROM style_jobs").fetchone() == (0,)
    finally:
        connection.close()


def test_html_and_epub_imports_are_cataloged_in_episode_order(
    client: TestClient,
) -> None:
    _create_project(client, "reference")
    html_response = _upload(
        client,
        source_type="html_file",
        filename="article.html",
        payload=b"<html><body><p>HTML body</p></body></html>",
        media_type="text/html",
    )
    assert html_response.status_code == 201
    assert _data(html_response)["reference_work_id"] == 1

    epub_response = _upload(
        client,
        source_type="epub",
        filename="book.epub",
        payload=_epub_payload(),
        media_type="application/epub+zip",
    )
    assert epub_response.status_code == 201
    epub_work_id = _data(epub_response)["reference_work_id"]
    episodes_response = client.get(
        f"/api/v1/projects/reference/style-analysis/reference-works/{epub_work_id}/episodes"
    )
    assert episodes_response.status_code == 200
    episodes = _data(episodes_response)
    assert [episode["title"] for episode in episodes] == ["First", "Episode 2"]
    assert [episode["order_index"] for episode in episodes] == [1, 2]


def test_catalog_reads_and_purge_are_project_scoped(
    client: TestClient,
) -> None:
    _create_project(client, "reference")
    _create_project(client, "other")
    imported = _upload(
        client,
        source_type="text",
        filename="book.txt",
        payload=b"body",
        media_type="text/plain",
    )
    work_id = _data(imported)["reference_work_id"]

    works_response = client.get(
        "/api/v1/projects/reference/style-analysis/reference-works"
    )
    assert works_response.status_code == 200
    works = _data(works_response)
    assert works[0]["reference_work_id"] == work_id
    assert works[0]["episode_count"] == 1

    detail_response = client.get(
        f"/api/v1/projects/reference/style-analysis/reference-works/{work_id}"
    )
    assert detail_response.status_code == 200
    detail = _data(detail_response)
    assert detail["source_type"] == "text"
    episode_id = client.get(
        f"/api/v1/projects/reference/style-analysis/reference-works/{work_id}/episodes"
    ).json()["data"][0]["reference_episode_id"]
    episode_response = client.get(
        f"/api/v1/projects/reference/style-analysis/reference-episodes/{episode_id}"
    )
    assert episode_response.status_code == 200
    assert _data(episode_response)["current_text_revision_id"] == 1

    cross_project = client.get(
        f"/api/v1/projects/other/style-analysis/reference-works/{work_id}"
    )
    assert cross_project.status_code == 404
    assert cross_project.json()["error"]["code"] == "NOT_FOUND"

    deleted = client.delete(
        f"/api/v1/projects/reference/style-analysis/reference-works/{work_id}"
    )
    assert deleted.status_code == 204
    assert (
        client.get("/api/v1/projects/reference/style-analysis/reference-works").json()[
            "data"
        ]
        == []
    )


@pytest.mark.parametrize(
    ("source_type", "filename", "payload", "expected_code"),
    [
        ("unknown", "book.txt", b"body", "SOURCE_TYPE_UNSUPPORTED"),
        ("text", "book.txt", b"\xff", "SOURCE_ENCODING_ERROR"),
        ("text", "book.txt", b"", "SOURCE_EMPTY"),
    ],
)
def test_source_errors_use_stable_error_codes(
    client: TestClient,
    source_type: str,
    filename: str,
    payload: bytes,
    expected_code: str,
) -> None:
    _create_project(client, "reference")
    response = _upload(
        client,
        source_type=source_type,
        filename=filename,
        payload=payload,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["details"]["domain_code"] == expected_code


def test_upload_size_limit_is_413_without_creating_rows(
    client: TestClient,
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_project(client, "reference")
    import novel_api.style_analysis.ingestion_service as ingestion_service

    monkeypatch.setattr(ingestion_service, "MAX_UPLOAD_BYTES", 3)
    response = _upload(
        client,
        source_type="text",
        filename="book.txt",
        payload=b"four",
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "SOURCE_TOO_LARGE"
    connection = sqlite3.connect(data_root / "reference" / "story.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM style_sources").fetchone() == (
            0,
        )
    finally:
        connection.close()


def test_malformed_source_is_all_or_nothing_and_does_not_create_job(
    client: TestClient,
    data_root: Path,
) -> None:
    _create_project(client, "reference")
    response = _upload(
        client,
        source_type="epub",
        filename="broken.epub",
        payload=b"not a zip",
    )
    assert response.status_code == 400
    connection = sqlite3.connect(data_root / "reference" / "story.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM style_sources").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM style_reference_works"
        ).fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM style_jobs").fetchone() == (0,)
    finally:
        connection.close()


def test_duplicate_import_race_converges_to_one_catalog(
    project_factory: Any,
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_factory("reference")
    target = ProjectTarget(
        project_id="reference",
        descriptor=ProjectDescriptor(
            project_dir=data_root / "reference",
            story_db=data_root / "reference" / "story.db",
        ),
    )
    payload = b"race-source"
    parse_barrier = Barrier(2)
    original_import_work = TextSourceAdapter.import_work

    def synchronized_import_work(self: TextSourceAdapter, request: Any) -> ImportedWork:
        imported = original_import_work(self, request)
        parse_barrier.wait(timeout=5)
        return imported

    monkeypatch.setattr(TextSourceAdapter, "import_work", synchronized_import_work)
    outcomes: list[Any] = []
    errors: list[BaseException] = []

    def run_import() -> None:
        try:
            outcomes.append(
                import_source(
                    target,
                    source_type="text",
                    filename="book.txt",
                    payload=payload,
                    media_type="text/plain",
                )
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [Thread(target=run_import) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert not errors
    assert sorted(outcome.reused_existing for outcome in outcomes) == [False, True]
    assert len({outcome.reference_work_id for outcome in outcomes}) == 1
    connection = sqlite3.connect(target.descriptor.story_db)
    try:
        for table in (
            "style_sources",
            "style_reference_works",
            "style_reference_episodes",
            "style_documents",
            "style_text_revisions",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (
                1,
            )
        assert connection.execute("SELECT COUNT(*) FROM style_jobs").fetchone() == (0,)
    finally:
        connection.close()


def test_persistence_failure_on_second_episode_rolls_back_entire_import(
    project_factory: Any,
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_factory("reference")
    target = ProjectTarget(
        project_id="reference",
        descriptor=ProjectDescriptor(
            project_dir=data_root / "reference",
            story_db=data_root / "reference" / "story.db",
        ),
    )
    imported_work = ImportedWork(
        title="Two Episodes",
        author_name=None,
        metadata={},
        episodes=(
            ImportedEpisode(
                external_episode_id="1",
                title="第一話",
                order_index=1,
                raw_text="本文一",
                metadata={"scene_break_offsets_raw": []},
            ),
            ImportedEpisode(
                external_episode_id="2",
                title="第二話",
                order_index=2,
                raw_text="本文二",
                metadata={"scene_break_offsets_raw": []},
            ),
        ),
    )
    original_import_work = TextSourceAdapter.import_work

    def two_episode_import_work(self: TextSourceAdapter, request: Any) -> ImportedWork:
        original_import_work(self, request)
        return imported_work

    monkeypatch.setattr(TextSourceAdapter, "import_work", two_episode_import_work)
    import novel_core.style_analysis.text_service as text_service_module

    original_insert = text_service_module.StyleTextService.insert_reference_revision
    calls = 0

    def fail_on_second_revision(self: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected second episode persistence failure")
        return original_insert(self, **kwargs)

    monkeypatch.setattr(
        text_service_module.StyleTextService,
        "insert_reference_revision",
        fail_on_second_revision,
    )

    with pytest.raises(RuntimeError, match="second episode"):
        import_source(
            target,
            source_type="text",
            filename="book.txt",
            payload=b"two-episode-source",
            media_type="text/plain",
        )

    connection = sqlite3.connect(target.descriptor.story_db)
    try:
        for table in (
            "style_sources",
            "style_source_snapshots",
            "style_reference_works",
            "style_reference_episodes",
            "style_documents",
            "style_text_revisions",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (
                0,
            )
        assert connection.execute("SELECT COUNT(*) FROM style_jobs").fetchone() == (0,)
    finally:
        connection.close()
