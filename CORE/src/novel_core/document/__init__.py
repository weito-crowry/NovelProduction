"""Database-independent Canonical Document Engine contracts."""

from __future__ import annotations

from .authoring import AuthoringResolution, import_plain_text, resolve_authoring
from .authoring_html import (
    AnnotationProjection,
    AuthoringBlockInput,
    parse_authoring_html,
    serialize_authoring_html,
)
from .exporters import ExportResult, ExportWarning, export_document
from .inline_html import (
    base_visible_text,
    normalize_inline_html,
    parse_inline_html,
    serialize_inline_html,
)
from .model import (
    BlockAttrs,
    BlockType,
    JsonValue,
    NovelBlock,
    NovelDocument,
    is_formal_block_id,
)
from .projections import (
    ContextProjectionResult,
    render_context_html,
    render_web_html,
)
from .schema import (
    new_block_id,
    normalize_document,
    parse_document_json,
    serialize_document_json,
)

__all__ = [
    "BlockAttrs",
    "BlockType",
    "AnnotationProjection",
    "AuthoringResolution",
    "AuthoringBlockInput",
    "ContextProjectionResult",
    "ExportResult",
    "ExportWarning",
    "JsonValue",
    "NovelBlock",
    "NovelDocument",
    "is_formal_block_id",
    "import_plain_text",
    "base_visible_text",
    "normalize_inline_html",
    "new_block_id",
    "normalize_document",
    "parse_inline_html",
    "parse_authoring_html",
    "parse_document_json",
    "render_context_html",
    "render_web_html",
    "resolve_authoring",
    "export_document",
    "serialize_authoring_html",
    "serialize_inline_html",
    "serialize_document_json",
]
