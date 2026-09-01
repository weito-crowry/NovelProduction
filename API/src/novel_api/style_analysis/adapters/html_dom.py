from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from novel_api.style_analysis.adapters.base import SourceParseError

_BLOCK_ELEMENTS = frozenset(
    {
        "address",
        "article",
        "blockquote",
        "div",
        "dl",
        "fieldset",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)
_EXCLUDED_ELEMENTS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
    }
)


@dataclass(frozen=True, slots=True)
class HtmlExtraction:
    raw_text: str
    scene_break_offsets_raw: tuple[int, ...]
    title: str | None


def extract_html_document(payload: bytes | str) -> HtmlExtraction:
    soup = BeautifulSoup(payload, "html.parser")
    root = _select_content_root(soup)
    for tag in list(root.find_all(tuple(_EXCLUDED_ELEMENTS))):
        tag.decompose()

    chunks: list[str] = []
    scene_break_offsets: list[int] = []
    boundary_pending = False

    def append_content(value: str) -> None:
        nonlocal boundary_pending
        if not value:
            return
        if boundary_pending and chunks:
            chunks.append("\n\n")
        boundary_pending = False
        chunks.append(value)

    def walk(node: object) -> None:
        nonlocal boundary_pending
        if isinstance(node, NavigableString):
            append_content(str(node))
            return
        if not isinstance(node, Tag):
            return
        name = node.name.lower()
        if name in _EXCLUDED_ELEMENTS:
            return
        if name == "br":
            append_content("\n")
            return
        if name == "hr":
            scene_break_offsets.append(sum(len(chunk) for chunk in chunks))
            return
        if name == "ruby":
            for child in node.children:
                if isinstance(child, Tag) and child.name.lower() in {"rt", "rp"}:
                    continue
                walk(child)
            return
        is_block = name in _BLOCK_ELEMENTS
        if is_block:
            boundary_pending = True
        for child in node.children:
            walk(child)
        if is_block:
            boundary_pending = True

    walk(root)
    raw_text = "".join(chunks)
    return HtmlExtraction(
        raw_text=raw_text,
        scene_break_offsets_raw=tuple(sorted(set(scene_break_offsets))),
        title=_document_title(soup),
    )


def _select_content_root(soup: BeautifulSoup) -> Tag:
    articles = soup.find_all("article")
    if len(articles) == 1:
        return articles[0]
    mains = soup.find_all("main")
    if len(mains) == 1:
        return mains[0]
    body = soup.body
    if body is None:
        raise SourceParseError("HTML source has no body")
    return body


def _document_title(soup: BeautifulSoup) -> str | None:
    title = soup.title
    if title is None:
        return None
    value = title.get_text()
    return value.strip() or None
