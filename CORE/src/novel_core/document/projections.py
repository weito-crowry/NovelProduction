"""Pure read and context projections for Canonical Documents."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from .inline_html import base_visible_text
from .model import NovelBlock, NovelDocument
from .schema import normalize_document

DEFAULT_CONTEXT_VISIBLE_CHARS = 4000


@dataclass(frozen=True, slots=True)
class ContextProjectionResult:
    """Context HTML plus the bounded tail-selection measurements."""

    html: str
    selected_block_count: int
    visible_text_char_count: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class PlainTextProjectionResult:
    """Plain text capture plus raw offsets for canonical scene-break hints."""

    raw_text: str
    scene_break_offsets_raw: tuple[int, ...]


def render_plain_text_projection(document: NovelDocument) -> PlainTextProjectionResult:
    """Project a Canonical Document into the bounded style-analysis text input."""

    normalized = normalize_document(document)
    parts: list[str] = []
    scene_break_offsets: list[int] = []
    for block in normalized.blocks:
        if block.type == "note":
            continue
        if block.type == "separator":
            scene_break_offsets.append(len("".join(parts)))
            continue
        if parts:
            parts.append("\n\n")
        parts.append(base_visible_text(block.html))
    return PlainTextProjectionResult(
        raw_text="".join(parts),
        scene_break_offsets_raw=tuple(sorted(set(scene_break_offsets))),
    )


def render_web_html(document: NovelDocument, *, include_notes: bool = False) -> str:
    """Render WEB Read HTML with block identity and minimal semantic typing."""

    normalized = normalize_document(document)
    return "\n".join(
        _render_block(block, include_id=True, include_context_metadata=False)
        for block in normalized.blocks
        if include_notes or block.type != "note"
    )


def render_context_html(
    document: NovelDocument,
    *,
    max_visible_chars: int = DEFAULT_CONTEXT_VISIBLE_CHARS,
) -> ContextProjectionResult:
    """Render a whole-block tail bounded by base-visible-text characters."""

    if isinstance(max_visible_chars, bool) or not isinstance(max_visible_chars, int):
        raise ValueError("max_visible_chars must be a non-negative integer")
    if max_visible_chars < 0:
        raise ValueError("max_visible_chars must be a non-negative integer")

    normalized = normalize_document(document)
    eligible = [
        (index, block)
        for index, block in enumerate(normalized.blocks)
        if block.type != "note"
    ]
    selected: list[tuple[int, NovelBlock]] = []
    visible_count = 0
    selected_substantive = False
    truncated = False
    for index, block in reversed(eligible):
        block_visible_count = len(base_visible_text(block.html))
        if block_visible_count == 0:
            selected.append((index, block))
            continue
        if not selected_substantive:
            selected.append((index, block))
            visible_count += block_visible_count
            selected_substantive = True
            continue
        if visible_count + block_visible_count <= max_visible_chars:
            selected.append((index, block))
            visible_count += block_visible_count
            continue
        truncated = True
        break

    selected.sort(key=lambda item: item[0])
    return ContextProjectionResult(
        html="\n".join(
            _render_block(block, include_id=False, include_context_metadata=True)
            for _, block in selected
        ),
        selected_block_count=len(selected),
        visible_text_char_count=visible_count,
        truncated=truncated,
    )


def _render_block(
    block: NovelBlock,
    *,
    include_id: bool,
    include_context_metadata: bool,
) -> str:
    if block.type == "heading":
        if block.attrs.heading_level is None:
            raise ValueError("heading_level is required")
        tag = f"h{block.attrs.heading_level}"
    elif block.type == "quote":
        tag = "blockquote"
    elif block.type == "separator":
        tag = "hr"
    else:
        tag = "p"

    attributes: list[tuple[str, str]] = []
    if include_id:
        attributes.append(("id", block.id))
    if tag == "p":
        attributes.append(("data-np-type", block.type))
    if include_context_metadata:
        if block.attrs.scene_id is not None:
            attributes.append(("data-np-scene-id", str(block.attrs.scene_id)))
        if block.attrs.speaker_character_id is not None:
            attributes.append(
                ("data-np-speaker-id", str(block.attrs.speaker_character_id))
            )
    serialized_attributes = "".join(
        f' {name}="{escape(value, quote=True)}"' for name, value in attributes
    )
    opening = f"<{tag}{serialized_attributes}>"
    if tag == "hr":
        return opening
    return f"{opening}{block.html}</{tag}>"
