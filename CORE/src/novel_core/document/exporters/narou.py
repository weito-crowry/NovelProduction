"""Direct Canonical Document renderer for Narou text."""

from __future__ import annotations

from novel_core.errors import DocumentSchemaError

from ..inline_html import _InlineNode, parse_inline_html
from ..model import NovelDocument
from ..schema import normalize_document
from . import ExportResult, ExportWarning


def render_narou(document: NovelDocument) -> ExportResult:
    """Render Canonical blocks directly as Narou-compatible plain text."""

    normalized = normalize_document(document)
    rendered_blocks: list[str] = []
    warnings: list[ExportWarning] = []
    for block in normalized.blocks:
        if block.type == "note":
            continue
        if block.type == "separator":
            rendered_blocks.append("＊　＊　＊")
            continue
        rendered_blocks.append(_render_block_inline(block.html, block.id, warnings))
    return ExportResult(
        format="narou",
        media_type="text/plain",
        content="\n\n".join(rendered_blocks),
        warnings=tuple(warnings),
    )


def _render_block_inline(
    fragment: str, block_id: str, warnings: list[ExportWarning]
) -> str:
    return "".join(
        _render_node(node, block_id, warnings) for node in parse_inline_html(fragment)
    )


def _render_node(
    node: _InlineNode, block_id: str, warnings: list[ExportWarning]
) -> str:
    if node.kind == "text":
        return node.text
    if node.kind == "br":
        return "\n"
    if node.kind == "ruby":
        base = "".join(
            _render_node(child, block_id, warnings) for child in node.children
        )
        if 1 <= len(base) <= 10 and 1 <= len(node.reading) <= 10:
            return f"｜{base}《{node.reading}》"
        warnings.append(
            ExportWarning(
                code="NAROU_RUBY_DEGRADED",
                message="ruby exceeded Narou's 1–10 character base or reading limit",
                block_id=block_id,
            )
        )
        return base
    if node.kind in {"strong", "em", "emphasis-dot"}:
        return "".join(
            _render_node(child, block_id, warnings) for child in node.children
        )
    raise DocumentSchemaError(f"unexpected inline node for Narou export: {node.kind}")
