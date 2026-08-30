"""Restricted Authoring HTML parsing, metadata codecs, and serialization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import Literal, cast

from novel_core.errors import DocumentSchemaError

from .inline_html import normalize_inline_html
from .model import BlockType, JsonValue, NovelDocument
from .schema import normalize_document

_OUTER_TAGS = frozenset({"p", "blockquote", "h1", "h2", "h3", "hr"})
_P_TYPES = frozenset({"narration", "dialogue", "thought", "description", "note"})
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
_ANNOTATION_KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STRUCTURAL_ATTRS = frozenset(
    {
        "id",
        "data-np-type",
        "data-np-scene-id",
        "data-np-speaker-id",
        "data-np-remove-annotations",
    }
)


@dataclass(frozen=True, slots=True)
class AuthoringBlockInput:
    """One parsed Authoring HTML block before parent-relative E2 resolution."""

    supplied_id: str | None
    type_hint: BlockType | None
    html: str
    attrs: dict[str, int | None] = field(default_factory=dict)
    annotations: dict[str, JsonValue] = field(default_factory=dict)
    remove_annotations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnnotationProjection:
    """Select the Canonical annotations safe to put in Authoring HTML."""

    mode: Literal["none", "selected", "all"]
    keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in {"none", "selected", "all"}:
            raise ValueError(f"unknown annotation projection mode: {self.mode}")
        object.__setattr__(self, "keys", tuple(self.keys))


def parse_authoring_html(raw: str) -> tuple[AuthoringBlockInput, ...]:
    """Parse strict outer Authoring HTML and preserve explicit metadata intent."""

    if not isinstance(raw, str):
        raise DocumentSchemaError("Authoring HTML must be a string")
    parser = _AuthoringParser()
    try:
        parser.feed(raw)
        parser.close()
    except DocumentSchemaError:
        raise
    except Exception as exc:
        raise DocumentSchemaError("invalid Authoring HTML") from exc
    if parser.current is not None:
        raise DocumentSchemaError("Authoring HTML contains an unclosed block")
    return tuple(parser.blocks)


def serialize_authoring_html(
    document: NovelDocument,
    annotation_projection: AnnotationProjection | None = None,
) -> str:
    """Render a Canonical Document as deterministic Restricted Authoring HTML."""

    normalized = normalize_document(document)
    projection = annotation_projection or AnnotationProjection("none")
    rendered: list[str] = []
    for block in normalized.blocks:
        tag = _outer_tag(block.type, block.attrs.heading_level)
        attributes = [("id", block.id)]
        if tag == "p":
            attributes.append(("data-np-type", block.type))
        if block.attrs.scene_id is not None:
            attributes.append(("data-np-scene-id", str(block.attrs.scene_id)))
        if block.attrs.speaker_character_id is not None:
            attributes.append(
                ("data-np-speaker-id", str(block.attrs.speaker_character_id))
            )
        attributes.extend(_project_annotation_attributes(block.annotations, projection))
        serialized_attributes = "".join(
            f' {name}="{escape(value, quote=True)}"' for name, value in attributes
        )
        opening = f"<{tag}{serialized_attributes}>"
        if tag == "hr":
            rendered.append(opening)
        else:
            rendered.append(f"{opening}{block.html}</{tag}>")
    return "\n".join(rendered)


class _AuthoringParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[AuthoringBlockInput] = []
        self.current: _OpenOuter | None = None
        self.seen_ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        source = self.get_starttag_text() or _source_start(tag, attrs)
        if self.current is not None:
            if tag in _OUTER_TAGS:
                raise DocumentSchemaError("nested Authoring block tags are forbidden")
            self.current.raw_html.append(source)
            return
        if tag not in _OUTER_TAGS:
            raise DocumentSchemaError(f"forbidden Authoring outer tag: {tag}")
        _validate_namespace_spelling(source)
        metadata = _parse_metadata(tag, attrs)
        if tag == "hr":
            self._append_block(metadata, "")
            return
        self.current = _OpenOuter(tag=tag, metadata=metadata)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        source = self.get_starttag_text() or _source_start(tag, attrs)
        if self.current is None:
            if tag != "hr":
                raise DocumentSchemaError(f"forbidden Authoring outer tag: {tag}")
            _validate_namespace_spelling(source)
            self._append_block(_parse_metadata(tag, attrs), "")
            return
        if tag in _OUTER_TAGS:
            raise DocumentSchemaError("nested Authoring block tags are forbidden")
        self.current.raw_html.append(source)

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            raise DocumentSchemaError("unexpected Authoring end tag")
        if tag in _OUTER_TAGS:
            if tag != self.current.tag:
                raise DocumentSchemaError("mismatched Authoring outer tag")
            current = self.current
            self.current = None
            normalized_html = normalize_inline_html("".join(current.raw_html))
            self._append_block(current.metadata, normalized_html)
            return
        self.current.raw_html.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.current is None:
            if data.strip():
                raise DocumentSchemaError("non-whitespace top-level text is forbidden")
            return
        self.current.raw_html.append(data)

    def handle_entityref(self, name: str) -> None:
        self._append_raw(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._append_raw(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        raise DocumentSchemaError("comments are not allowed in Authoring HTML")

    def handle_decl(self, decl: str) -> None:
        raise DocumentSchemaError("declarations are not allowed in Authoring HTML")

    def handle_pi(self, data: str) -> None:
        raise DocumentSchemaError(
            "processing instructions are not allowed in Authoring HTML"
        )

    def unknown_decl(self, data: str) -> None:
        raise DocumentSchemaError(
            "unknown declarations are not allowed in Authoring HTML"
        )

    def _append_raw(self, source: str) -> None:
        if self.current is None:
            if source.strip():
                raise DocumentSchemaError("non-whitespace top-level text is forbidden")
        else:
            self.current.raw_html.append(source)

    def _append_block(self, metadata: _BlockMetadata, html: str) -> None:
        if metadata.supplied_id is not None:
            if metadata.supplied_id in self.seen_ids:
                raise DocumentSchemaError("supplied block IDs must be unique")
            self.seen_ids.add(metadata.supplied_id)
        self.blocks.append(
            AuthoringBlockInput(
                supplied_id=metadata.supplied_id,
                type_hint=metadata.type_hint,
                html=html,
                attrs=metadata.attrs,
                annotations=metadata.annotations,
                remove_annotations=metadata.remove_annotations,
            )
        )


@dataclass(frozen=True, slots=True)
class _BlockMetadata:
    supplied_id: str | None
    type_hint: BlockType | None
    attrs: dict[str, int | None]
    annotations: dict[str, JsonValue]
    remove_annotations: tuple[str, ...]


@dataclass(slots=True)
class _OpenOuter:
    tag: str
    metadata: _BlockMetadata
    raw_html: list[str] = field(default_factory=list)


def _parse_metadata(tag: str, attrs: list[tuple[str, str | None]]) -> _BlockMetadata:
    names = [name for name, _ in attrs]
    if len(names) != len(set(names)):
        raise DocumentSchemaError("duplicate Authoring attributes are forbidden")
    values = dict(attrs)
    for name in values:
        if name in _STRUCTURAL_ATTRS or name.startswith("data-ann-"):
            continue
        if name.startswith("data-np-"):
            raise DocumentSchemaError(f"unknown data-np attribute: {name}")
        raise DocumentSchemaError(f"unknown Authoring attribute: {name}")

    supplied_id = values.get("id")
    if supplied_id == "":
        raise DocumentSchemaError("id cannot be empty")
    if "id" in values and supplied_id is None:
        raise DocumentSchemaError("id must have a value")

    if tag == "p":
        type_value = values.get("data-np-type")
        if type_value == "":
            raise DocumentSchemaError("data-np-type cannot be empty")
        if type_value is not None and type_value not in _P_TYPES:
            raise DocumentSchemaError("data-np-type is invalid for p")
        type_hint = cast(BlockType | None, type_value)
    else:
        if "data-np-type" in values:
            raise DocumentSchemaError("forced Authoring tags cannot set data-np-type")
        type_hint = cast(
            BlockType,
            {
                "blockquote": "quote",
                "h1": "heading",
                "h2": "heading",
                "h3": "heading",
                "hr": "separator",
            }[tag],
        )

    explicit_attrs: dict[str, int | None] = {}
    for name, output_name in (
        ("data-np-scene-id", "scene_id"),
        ("data-np-speaker-id", "speaker_character_id"),
    ):
        if name not in values:
            continue
        raw_value = values[name]
        if raw_value is None:
            raise DocumentSchemaError(f"{name} must have a value")
        if raw_value == "":
            explicit_attrs[output_name] = None
        elif not re.fullmatch(r"[0-9]+", raw_value) or int(raw_value) <= 0:
            raise DocumentSchemaError(f"{name} must be a positive decimal integer")
        else:
            explicit_attrs[output_name] = int(raw_value)
    if tag in {"h1", "h2", "h3"}:
        explicit_attrs["heading_level"] = int(tag[1])

    annotations: dict[str, JsonValue] = {}
    for name, raw_value in attrs:
        if not name.startswith("data-ann-"):
            continue
        key = name.removeprefix("data-ann-")
        if not _ANNOTATION_KEY.fullmatch(key):
            raise DocumentSchemaError(
                "annotation keys must be lowercase ASCII kebab-case"
            )
        if raw_value is None:
            raise DocumentSchemaError(f"{name} must have a string value")
        if key == "emotions":
            decoded = _decode_json(raw_value, f"{name} must be a JSON string array")
            if not isinstance(decoded, list) or any(
                not isinstance(item, str) for item in decoded
            ):
                raise DocumentSchemaError(
                    "data-ann-emotions must be a JSON string array"
                )
            annotations[key] = decoded
        else:
            annotations[key] = raw_value

    remove_annotations: tuple[str, ...] = ()
    if "data-np-remove-annotations" in values:
        raw_removals = values["data-np-remove-annotations"]
        if raw_removals is None:
            raise DocumentSchemaError("data-np-remove-annotations must have a value")
        decoded = _decode_json(
            raw_removals, "data-np-remove-annotations must be a JSON string array"
        )
        if not isinstance(decoded, list) or any(
            not isinstance(item, str) or not item for item in decoded
        ):
            raise DocumentSchemaError(
                "annotation removal keys must be non-empty strings"
            )
        if len(decoded) != len(set(decoded)):
            raise DocumentSchemaError("duplicate annotation removal keys are forbidden")
        remove_annotations = tuple(decoded)

    return _BlockMetadata(
        supplied_id=supplied_id,
        type_hint=type_hint,
        attrs=explicit_attrs,
        annotations=annotations,
        remove_annotations=remove_annotations,
    )


def _decode_json(raw: str, message: str) -> object:
    try:
        return json.loads(
            raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise DocumentSchemaError(message) from exc


def _outer_tag(block_type: BlockType, heading_level: int | None) -> str:
    if block_type == "quote":
        return "blockquote"
    if block_type == "heading":
        if heading_level is None:
            raise DocumentSchemaError("heading_level is required")
        return f"h{heading_level}"
    if block_type == "separator":
        return "hr"
    return "p"


def _project_annotation_attributes(
    annotations: dict[str, JsonValue], projection: AnnotationProjection
) -> list[tuple[str, str]]:
    if projection.mode == "none":
        return []
    keys = set(annotations) if projection.mode == "all" else set(projection.keys)
    rendered: list[tuple[str, str]] = []
    for key in sorted(keys):
        if not _ANNOTATION_KEY.fullmatch(key) or key not in annotations:
            continue
        value = annotations[key]
        if key == "emotions":
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                rendered.append(
                    (
                        f"data-ann-{key}",
                        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                    )
                )
        elif isinstance(value, str):
            rendered.append((f"data-ann-{key}", value))
    return rendered


def _source_start(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    rendered = "".join(
        f" {name}" if value is None else f' {name}="{escape(value, quote=True)}"'
        for name, value in attrs
    )
    return f"<{tag}{rendered}>"


def _validate_namespace_spelling(source: str) -> None:
    match = re.match(r"<\s*[^\s/>]+", source)
    if match is None:
        return

    position = match.end()
    while position < len(source):
        while position < len(source) and source[position].isspace():
            position += 1
        if position >= len(source) or source[position] in "/>":
            return

        name_start = position
        while (
            position < len(source)
            and not source[position].isspace()
            and source[position] not in "=/>"
        ):
            position += 1
        if position == name_start:
            position += 1
            continue

        name = source[name_start:position]
        if name.lower().startswith(("data-ann-", "data-np-")) and name != name.lower():
            raise DocumentSchemaError(
                "data annotation and metadata names must be lowercase"
            )

        while position < len(source) and source[position].isspace():
            position += 1
        if position >= len(source) or source[position] != "=":
            continue

        position += 1
        while position < len(source) and source[position].isspace():
            position += 1
        if position >= len(source):
            return
        if source[position] in "\"'":
            quote = source[position]
            position += 1
            while position < len(source) and source[position] != quote:
                position += 1
            if position < len(source):
                position += 1
            continue
        while (
            position < len(source)
            and not source[position].isspace()
            and source[position] != ">"
        ):
            position += 1
