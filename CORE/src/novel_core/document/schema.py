"""Strict parsing, normalization, and serialization for Schema v1."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Mapping

from novel_core.errors import DocumentSchemaError

from .inline_html import base_visible_text, normalize_inline_html
from .model import (
    BlockAttrs,
    JsonValue,
    NovelBlock,
    NovelDocument,
    is_formal_block_id,
)

_DOCUMENT_KEYS = frozenset({"schema_version", "type", "blocks"})
_BLOCK_KEYS = frozenset({"id", "type", "html", "attrs", "annotations"})
_ATTR_KEYS = frozenset({"scene_id", "speaker_character_id", "heading_level"})
_BLOCK_TYPES = frozenset(
    {
        "narration",
        "dialogue",
        "thought",
        "description",
        "quote",
        "heading",
        "separator",
        "note",
    }
)


def new_block_id() -> str:
    """Generate a formal opaque block ID from a UUID4."""

    return f"blk_{uuid.uuid4().hex}"


def parse_document_json(
    raw: str | bytes | bytearray | Mapping[str, object],
) -> NovelDocument:
    """Parse and structurally validate a Canonical Document JSON value."""

    value = _load_json(raw)
    if not isinstance(value, Mapping):
        raise _error("document must be a JSON object")

    _require_exact_keys(value, _DOCUMENT_KEYS, "document")
    version = value["schema_version"]
    if version != 1 or isinstance(version, bool):
        raise _error(f"unsupported schema_version: {version!r}")

    document_type = value["type"]
    if document_type != "novel_document":
        raise _error("document type must be 'novel_document'")

    blocks = value["blocks"]
    if not isinstance(blocks, list):
        raise _error("blocks must be an array")

    parsed_blocks: list[NovelBlock] = []
    seen_ids: set[str] = set()
    for index, block_value in enumerate(blocks):
        parsed = _parse_block(block_value, index)
        if parsed.id in seen_ids:
            raise _error(f"duplicate block id: {parsed.id}")
        seen_ids.add(parsed.id)
        parsed_blocks.append(parsed)

    return normalize_document(
        NovelDocument(
            schema_version=1, type="novel_document", blocks=tuple(parsed_blocks)
        )
    )


def normalize_document(document: NovelDocument) -> NovelDocument:
    """Validate and return a deterministic normalized document value."""

    if not isinstance(document, NovelDocument):
        raise _error("document must be a NovelDocument")
    if document.schema_version != 1 or isinstance(document.schema_version, bool):
        raise _error("schema_version must be 1")
    if document.type != "novel_document":
        raise _error("document type must be 'novel_document'")
    if not isinstance(document.blocks, tuple):
        raise _error("blocks must be a tuple")

    seen_ids: set[str] = set()
    normalized_blocks: list[NovelBlock] = []
    for index, block in enumerate(document.blocks):
        normalized = _normalize_block(block, index)
        if normalized.id in seen_ids:
            raise _error(f"duplicate block id: {normalized.id}")
        seen_ids.add(normalized.id)
        normalized_blocks.append(normalized)
    return NovelDocument(blocks=tuple(normalized_blocks))


def serialize_document_json(document: NovelDocument) -> str:
    """Serialize a normalized document with stable compact JSON formatting."""

    normalized = normalize_document(document)
    payload = {
        "schema_version": normalized.schema_version,
        "type": normalized.type,
        "blocks": [
            {
                "id": block.id,
                "type": block.type,
                "html": block.html,
                "attrs": _attrs_to_json(block.attrs),
                "annotations": _sorted_json_object(block.annotations),
            }
            for block in normalized.blocks
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _load_json(raw: str | bytes | bytearray | Mapping[str, object]) -> object:
    if isinstance(raw, Mapping):
        return raw
    if not isinstance(raw, (str, bytes, bytearray)):
        raise _error("raw document must be JSON text or an object")
    try:
        return json.loads(raw, parse_constant=_reject_non_finite)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("invalid JSON") from exc


def _reject_non_finite(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _parse_block(value: object, index: int) -> NovelBlock:
    if not isinstance(value, Mapping):
        raise _error(f"block {index} must be an object")
    _require_exact_keys(value, _BLOCK_KEYS, f"block {index}")
    return _normalize_block(
        NovelBlock(
            id=value["id"],
            type=value["type"],
            html=value["html"],
            attrs=_parse_attrs(value["attrs"], index),
            annotations=_parse_annotations(value["annotations"], index),
        ),
        index,
    )


def _normalize_block(block: object, index: int) -> NovelBlock:
    if not isinstance(block, NovelBlock):
        raise _error(f"block {index} must be a NovelBlock")
    if not is_formal_block_id(block.id):
        raise _error(f"block {index} has an invalid formal id")
    if block.type not in _BLOCK_TYPES:
        raise _error(f"block {index} has an unknown type")
    if not isinstance(block.html, str):
        raise _error(f"block {index}.html must be a string")
    attrs = _normalize_attrs(block.attrs, block.type, index)
    annotations = _normalize_annotations(block.annotations, index)
    normalized_html = normalize_inline_html(block.html)
    if block.type == "heading":
        if attrs.heading_level is None:
            raise _error(f"block {index} heading_level is required")
        if not base_visible_text(normalized_html).strip():
            raise _error(f"block {index} heading html must have visible text")
    elif attrs.heading_level is not None:
        raise _error(f"block {index} heading_level is only valid for headings")
    if block.type == "separator" and block.html != "":
        raise _error(f"block {index} separator html must be empty")
    return NovelBlock(
        id=block.id,
        type=block.type,
        html=normalized_html,
        attrs=attrs,
        annotations=annotations,
    )


def _parse_attrs(value: object, index: int) -> BlockAttrs:
    if not isinstance(value, Mapping):
        raise _error(f"block {index}.attrs must be an object")
    _require_known_keys(value, _ATTR_KEYS, f"block {index}.attrs")
    return BlockAttrs(
        scene_id=value.get("scene_id"),
        speaker_character_id=value.get("speaker_character_id"),
        heading_level=value.get("heading_level"),
    )


def _normalize_attrs(attrs: object, block_type: str, index: int) -> BlockAttrs:
    if not isinstance(attrs, BlockAttrs):
        raise _error(f"block {index}.attrs must be BlockAttrs")
    for name, value in (
        ("scene_id", attrs.scene_id),
        ("speaker_character_id", attrs.speaker_character_id),
    ):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            raise _error(f"block {index}.{name} must be a positive integer or null")
    if attrs.heading_level is not None and (
        isinstance(attrs.heading_level, bool)
        or not isinstance(attrs.heading_level, int)
        or not 1 <= attrs.heading_level <= 3
    ):
        raise _error(f"block {index}.heading_level must be an integer from 1 through 3")
    if block_type == "heading" and attrs.heading_level is None:
        raise _error(f"block {index} heading_level is required")
    if block_type != "heading" and attrs.heading_level is not None:
        raise _error(f"block {index} heading_level is only valid for headings")
    return BlockAttrs(
        scene_id=attrs.scene_id,
        speaker_character_id=attrs.speaker_character_id,
        heading_level=attrs.heading_level if block_type == "heading" else None,
    )


def _parse_annotations(value: object, index: int) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise _error(f"block {index}.annotations must be an object")
    return _normalize_annotations(value, index)


def _normalize_annotations(value: object, index: int) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise _error(f"block {index}.annotations must be an object")
    normalized: dict[str, JsonValue] = {}
    for key, annotation in value.items():
        if not isinstance(key, str) or not key:
            raise _error(f"block {index} annotation keys must be non-empty strings")
        normalized[key] = _normalize_json_value(
            annotation, f"block {index} annotation {key!r}"
        )
    if "emotions" in normalized:
        emotions = normalized["emotions"]
        if not isinstance(emotions, list) or any(
            not isinstance(item, str) for item in emotions
        ):
            raise _error("annotations.emotions must be an array of strings")
    return _sorted_json_object(normalized)


def _normalize_json_value(value: object, context: str) -> JsonValue:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _error(f"{context} must be finite")
        return value
    if isinstance(value, list):
        return [_normalize_json_value(item, context) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _error(f"{context} object keys must be strings")
            normalized[key] = _normalize_json_value(item, context)
        return _sorted_json_object(normalized)
    raise _error(f"{context} is not a standard JSON value")


def _sorted_json_object(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: value[key] for key in sorted(value)}


def _attrs_to_json(attrs: BlockAttrs) -> dict[str, int]:
    values: dict[str, int] = {}
    if attrs.heading_level is not None:
        values["heading_level"] = attrs.heading_level
    if attrs.scene_id is not None:
        values["scene_id"] = attrs.scene_id
    if attrs.speaker_character_id is not None:
        values["speaker_character_id"] = attrs.speaker_character_id
    return {key: values[key] for key in sorted(values)}


def _require_exact_keys(
    value: Mapping[object, object], expected: frozenset[str], context: str
) -> None:
    keys = set(value)
    if keys != expected:
        raise _error(f"{context} fields must be exactly {sorted(expected)!r}")
    if any(not isinstance(key, str) for key in keys):
        raise _error(f"{context} field names must be strings")


def _require_known_keys(
    value: Mapping[object, object], allowed: frozenset[str], context: str
) -> None:
    if any(not isinstance(key, str) or key not in allowed for key in value):
        raise _error(f"{context} contains an unknown field")


def _error(message: str) -> DocumentSchemaError:
    return DocumentSchemaError(message)
