from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from novel_api.style_analysis.adapters import get_source_adapter
from novel_api.style_analysis.adapters.base import (
    SourceEmptyError,
    SourceEncodingError,
    SourceParseError,
    SourceRequest,
    SourceTooLargeError,
)


def test_source_adapter_registry_exposes_fixed_v1_adapters() -> None:
    assert get_source_adapter("text").adapter_id == "style-source-text"
    assert get_source_adapter("html_file").adapter_id == "style-source-html-file"
    assert get_source_adapter("epub").adapter_id == "style-source-epub"
    assert {
        get_source_adapter(kind).adapter_version
        for kind in ("text", "html_file", "epub")
    } == {1}


def test_text_adapter_identity_is_upload_bytes_sha256() -> None:
    payload = "第一行\n\n第二行".encode()
    request = SourceRequest(source_type="text", filename="sample.txt", payload=payload)

    identity = get_source_adapter("text").identify(request)

    assert identity.external_work_id == hashlib.sha256(payload).hexdigest()


def test_text_adapter_accepts_utf8_bom_and_emits_one_episode() -> None:
    request = SourceRequest(
        source_type="text",
        filename="sample.txt",
        payload="本文\n\n続き".encode("utf-8-sig"),
    )

    imported = get_source_adapter("text").import_work(request)

    assert imported.title == "sample"
    assert imported.author_name is None
    assert len(imported.episodes) == 1
    assert imported.episodes[0].external_episode_id == "1"
    assert imported.episodes[0].title == "sample"
    assert imported.episodes[0].order_index == 1
    assert imported.episodes[0].raw_text == "本文\n\n続き"
    assert imported.episodes[0].metadata == {"scene_break_offsets_raw": []}


def test_text_adapter_rejects_invalid_utf8() -> None:
    request = SourceRequest(source_type="text", filename="sample.txt", payload=b"\xff")

    with pytest.raises(SourceEncodingError):
        get_source_adapter("text").import_work(request)


def test_text_adapter_rejects_empty_text() -> None:
    request = SourceRequest(
        source_type="text",
        filename="sample.txt",
        payload=b"\xef\xbb\xbf",
    )

    with pytest.raises(SourceEmptyError):
        get_source_adapter("text").import_work(request)


def test_html_adapter_selects_article_and_serializes_supported_dom_nodes() -> None:
    payload = (
        "<html><head><title>HTML title</title></head><body>"
        "<main>wrong root</main>"
        "<article><header>ignored header</header>"
        "<p>第一</p><p>第二<br>行</p>"
        "<p><ruby>漢<rt>かん</rt><rp>(</rp><rp>かん</rp><rp>)</rp></ruby></p>"
        "<hr><p>第三</p>"
        "<script>ignored script</script><nav>ignored nav</nav>"
        "</article></body></html>"
    ).encode()

    imported = get_source_adapter("html_file").import_work(
        SourceRequest(
            source_type="html_file", filename="fallback.html", payload=payload
        )
    )

    assert imported.title == "HTML title"
    assert imported.episodes[0].raw_text == "第一\n\n第二\n行\n\n漢\n\n第三"
    assert imported.episodes[0].metadata == {"scene_break_offsets_raw": [11]}


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        (
            ("<html><body><article>article</article><main>main</main></body></html>"),
            "article",
        ),
        (
            (
                "<html><body><article>a</article><article>b</article>"
                "<main>main</main></body></html>"
            ),
            "main",
        ),
        ("<html><body><div>body</div></body></html>", "body"),
    ],
)
def test_html_adapter_root_precedence(markup: str, expected: str) -> None:
    imported = get_source_adapter("html_file").import_work(
        SourceRequest(
            source_type="html_file", filename="book.html", payload=markup.encode()
        )
    )

    assert imported.episodes[0].raw_text == expected


def test_html_adapter_rejects_missing_body_and_empty_content() -> None:
    adapter = get_source_adapter("html_file")

    with pytest.raises(SourceParseError):
        adapter.import_work(
            SourceRequest(
                source_type="html_file", filename="book.html", payload=b"<html />"
            )
        )
    with pytest.raises(SourceEmptyError):
        adapter.import_work(
            SourceRequest(
                source_type="html_file",
                filename="book.html",
                payload=b"<html><body><main><p></p></main></body></html>",
            )
        )


def test_html_adapter_preserves_br_line_feeds_at_document_edges() -> None:
    imported = get_source_adapter("html_file").import_work(
        SourceRequest(
            source_type="html_file",
            filename="book.html",
            payload=b"<html><body><br>body<br></body></html>",
        )
    )

    assert imported.episodes[0].raw_text == "\nbody\n"


def _epub_bytes(*, bad_href: str | None = None) -> bytes:
    href = bad_href or "chapter-1.xhtml"
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = f"""<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" unique-identifier="book-id">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>EPUB Book</dc:title><dc:creator>Author</dc:creator>
      </metadata>
      <manifest>
        <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"
              properties="nav"/>
        <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"
              properties="cover-image"/>
        <item id="one" href="{href}" media-type="application/xhtml+xml"/>
        <item id="two" href="chapter-2.xhtml" media-type="application/xhtml+xml"/>
        <item id="three" href="chapter-3.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine toc="ncx">
        <itemref idref="nav"/><itemref idref="cover"/>
        <itemref idref="one"/><itemref idref="two"/><itemref idref="three"/>
      </spine>
    </package>"""
    files = {
        "META-INF/container.xml": container,
        "OEBPS/content.opf": opf,
        "OEBPS/nav.xhtml": (
            '<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav '
            'epub:type="toc"><ol><li><a href="chapter-1.xhtml">第一章</a>'
            "</li></ol></nav></body></html>"
        ),
        "OEBPS/cover.xhtml": "<html><body><h1>Cover</h1></body></html>",
        "OEBPS/chapter-1.xhtml": "<html><body><p>一</p></body></html>",
        "OEBPS/chapter-2.xhtml": "<html><body><h1>第二章</h1><p>二</p></body></html>",
        "OEBPS/chapter-3.xhtml": "<html><body><p>三</p></body></html>",
    }
    if bad_href is not None:
        files.pop("OEBPS/chapter-1.xhtml", None)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_epub_adapter_reads_metadata_spine_nav_and_title_fallbacks() -> None:
    imported = get_source_adapter("epub").import_work(
        SourceRequest(source_type="epub", filename="upload.epub", payload=_epub_bytes())
    )

    assert imported.title == "EPUB Book"
    assert imported.author_name == "Author"
    assert [episode.external_episode_id for episode in imported.episodes] == [
        "spine:1",
        "spine:2",
        "spine:3",
    ]
    assert [episode.title for episode in imported.episodes] == [
        "第一章",
        "第二章",
        "Episode 3",
    ]
    assert [episode.raw_text for episode in imported.episodes] == [
        "一",
        "第二章\n\n二",
        "三",
    ]
    assert all(
        episode.metadata == {"scene_break_offsets_raw": []}
        for episode in imported.episodes
    )


def test_epub_adapter_rejects_archive_path_escape() -> None:
    for bad_href in ("../../escape.xhtml", r"..\escape.xhtml"):
        with pytest.raises(SourceParseError):
            get_source_adapter("epub").import_work(
                SourceRequest(
                    source_type="epub",
                    filename="upload.epub",
                    payload=_epub_bytes(bad_href=bad_href),
                )
            )


def test_epub_adapter_reports_selected_spine_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_getinfo = zipfile.ZipFile.getinfo

    def oversized_getinfo(self: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
        info = original_getinfo(self, name)
        if name in {
            "OEBPS/chapter-1.xhtml",
            "OEBPS/chapter-2.xhtml",
            "OEBPS/chapter-3.xhtml",
        }:
            info.file_size = 200 * 1024 * 1024
        return info

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", oversized_getinfo)

    with pytest.raises(SourceTooLargeError):
        get_source_adapter("epub").import_work(
            SourceRequest(
                source_type="epub", filename="upload.epub", payload=_epub_bytes()
            )
        )
