"""Strict Restricted Inline HTML parsing and canonical rendering."""

from __future__ import annotations

import html as html_module
from dataclasses import dataclass, field
from html.parser import HTMLParser

from novel_core.errors import DocumentSchemaError


@dataclass(frozen=True, slots=True)
class _InlineNode:
    kind: str
    text: str = ""
    children: tuple[_InlineNode, ...] = ()
    reading: str = ""


@dataclass(slots=True)
class _OpenNode:
    tag: str
    kind: str
    children: list[_InlineNode] = field(default_factory=list)


InlineFragment = tuple[_InlineNode, ...]
_ALLOWED_TAGS = frozenset({"strong", "em", "ruby", "rt", "br"})


def parse_inline_html(fragment: str) -> InlineFragment:
    """Parse a Restricted Inline HTML fragment without browser repair."""

    if not isinstance(fragment, str):
        raise DocumentSchemaError("inline HTML must be a string")
    parser = _InlineParser()
    try:
        parser.feed(fragment)
        parser.close()
    except DocumentSchemaError:
        raise
    except Exception as exc:
        raise DocumentSchemaError("invalid inline HTML") from exc
    if parser.stack:
        raise DocumentSchemaError("inline HTML contains an unclosed element")
    return tuple(parser.root)


def serialize_inline_html(parsed: InlineFragment) -> str:
    """Serialize a parsed fragment using one deterministic HTML spelling."""

    if not isinstance(parsed, tuple):
        raise DocumentSchemaError("parsed inline HTML must be a tuple")
    return "".join(_serialize_node(node) for node in parsed)


def normalize_inline_html(fragment: str) -> str:
    """Parse and serialize a Restricted Inline HTML fragment."""

    normalized_line_endings = fragment.replace("\r\n", "\n").replace("\r", "\n")
    return serialize_inline_html(parse_inline_html(normalized_line_endings))


def base_visible_text(fragment: str | InlineFragment) -> str:
    """Return visible base text, excluding ruby readings."""

    parsed = parse_inline_html(fragment) if isinstance(fragment, str) else fragment
    return "".join(_visible_text(node) for node in parsed)


class _InlineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root: list[_InlineNode] = []
        self.stack: list[_OpenNode] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        if tag == "br":
            raise DocumentSchemaError("br cannot have an end tag")
        if tag not in _ALLOWED_TAGS or not self.stack or self.stack[-1].tag != tag:
            raise DocumentSchemaError("mismatched or forbidden inline end tag")
        opened = self.stack.pop()
        node = self._finish(opened)
        self._append(node)

    def handle_data(self, data: str) -> None:
        if data:
            self._append(_InlineNode(kind="text", text=data))

    def handle_entityref(self, name: str) -> None:
        self._append(_InlineNode(kind="text", text=html_module.unescape(f"&{name};")))

    def handle_charref(self, name: str) -> None:
        self._append(_InlineNode(kind="text", text=html_module.unescape(f"&#{name};")))

    def handle_comment(self, data: str) -> None:
        raise DocumentSchemaError("comments are not allowed in inline HTML")

    def handle_decl(self, decl: str) -> None:
        raise DocumentSchemaError("declarations are not allowed in inline HTML")

    def handle_pi(self, data: str) -> None:
        raise DocumentSchemaError(
            "processing instructions are not allowed in inline HTML"
        )

    def unknown_decl(self, data: str) -> None:
        raise DocumentSchemaError("unknown declarations are not allowed in inline HTML")

    def _start(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        self_closing: bool,
    ) -> None:
        if tag not in _ALLOWED_TAGS:
            raise DocumentSchemaError(f"forbidden inline tag: {tag}")
        if tag == "br":
            if attrs or not self_closing and tag == "br":
                if attrs:
                    raise DocumentSchemaError("br cannot have attributes")
            self._append(_InlineNode(kind="br"))
            return
        if self_closing:
            raise DocumentSchemaError("non-void inline tags cannot self-close")
        kind = self._validate_attrs(tag, attrs)
        if tag == "rt" and (not self.stack or self.stack[-1].tag != "ruby"):
            raise DocumentSchemaError("rt is only allowed directly inside ruby")
        self.stack.append(_OpenNode(tag=tag, kind=kind))

    def _validate_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        names = [name for name, _ in attrs]
        if len(names) != len(set(names)):
            raise DocumentSchemaError("duplicate inline attributes are not allowed")
        if tag == "em":
            if not attrs:
                return "em"
            if len(attrs) == 1 and attrs[0] == ("data-emphasis", "dot"):
                return "emphasis-dot"
            raise DocumentSchemaError("em only accepts data-emphasis=dot")
        if attrs:
            raise DocumentSchemaError(f"{tag} cannot have attributes")
        return tag

    def _append(self, node: _InlineNode) -> None:
        if self.stack:
            self.stack[-1].children.append(node)
        else:
            self.root.append(node)

    def _finish(self, opened: _OpenNode) -> _InlineNode:
        children = tuple(opened.children)
        if opened.tag == "ruby":
            if not children or children[-1].kind != "rt":
                raise DocumentSchemaError("ruby must end with exactly one rt")
            rt_nodes = [node for node in children if node.kind == "rt"]
            if len(rt_nodes) != 1:
                raise DocumentSchemaError("ruby must contain exactly one rt")
            rt = rt_nodes[0]
            base_nodes = children[:-1]
            if not base_nodes or not all(node.kind == "text" for node in base_nodes):
                raise DocumentSchemaError("ruby base must contain plain text only")
            if not _node_text(base_nodes).strip() or not rt.text.strip():
                raise DocumentSchemaError("ruby base and reading must be non-empty")
            return _InlineNode(kind="ruby", children=base_nodes, reading=rt.text)
        if opened.tag == "rt":
            if not children or not all(node.kind == "text" for node in children):
                raise DocumentSchemaError("ruby reading must contain plain text only")
            reading = _node_text(children)
            if not reading.strip():
                raise DocumentSchemaError("ruby reading must be non-empty")
            return _InlineNode(kind="rt", text=reading)
        return _InlineNode(kind=opened.kind, children=children)


def _serialize_node(node: _InlineNode) -> str:
    if node.kind == "text":
        return html_module.escape(node.text, quote=True)
    if node.kind == "br":
        return "<br>"
    if node.kind == "ruby":
        return (
            "<ruby>"
            + "".join(_serialize_node(child) for child in node.children)
            + "<rt>"
            + html_module.escape(node.reading, quote=True)
            + "</rt></ruby>"
        )
    if node.kind == "strong":
        return (
            "<strong>"
            + "".join(_serialize_node(child) for child in node.children)
            + "</strong>"
        )
    if node.kind == "em":
        return (
            "<em>"
            + "".join(_serialize_node(child) for child in node.children)
            + "</em>"
        )
    if node.kind == "emphasis-dot":
        return (
            '<em data-emphasis="dot">'
            + "".join(_serialize_node(child) for child in node.children)
            + "</em>"
        )
    raise DocumentSchemaError(f"unknown inline AST node: {node.kind}")


def _visible_text(node: _InlineNode) -> str:
    if node.kind == "text":
        return node.text
    if node.kind == "br":
        return "\n"
    return "".join(_visible_text(child) for child in node.children)


def _node_text(nodes: tuple[_InlineNode, ...]) -> str:
    return "".join(node.text for node in nodes)
