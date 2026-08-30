"""Database-independent parent-relative Canonical Document authoring."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from html import escape
from typing import cast

from novel_core.errors import DocumentSchemaError, ValidationError

from .authoring_html import AuthoringBlockInput, parse_authoring_html
from .model import BlockAttrs, JsonValue, NovelBlock, NovelDocument
from .schema import new_block_id, normalize_document

_ATTR_NAMES = frozenset({"scene_id", "speaker_character_id", "heading_level"})
_PATCH_NAMES = frozenset({"attrs", "annotations", "remove_annotations"})


@dataclass(frozen=True, slots=True)
class AuthoringResolution:
    """The resolved Canonical snapshot and same-request ID translations."""

    document: NovelDocument
    id_map: dict[str, str]


@dataclass(frozen=True, slots=True)
class _MetadataPatch:
    attrs: dict[str, object]
    annotations: dict[str, JsonValue]
    remove_annotations: tuple[str, ...]


def import_plain_text(text: str) -> NovelDocument:
    """Import plain prose into narration blocks without semantic inference."""

    if not isinstance(text, str):
        raise DocumentSchemaError("plain_text must be a string")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    return normalize_document(
        NovelDocument(
            blocks=tuple(
                NovelBlock(
                    id=new_block_id(),
                    type="narration",
                    html=escape("\n".join(group), quote=False).replace("\n", "<br>"),
                )
                for group in groups
            )
        )
    )


def resolve_authoring(
    parent: NovelDocument | None,
    html: str | None,
    metadata_updates: Mapping[str, object] | None,
) -> AuthoringResolution:
    """Resolve a complete HTML snapshot and/or metadata patches relative to parent."""

    normalized_parent = None if parent is None else normalize_document(parent)
    if html is None and normalized_parent is None:
        raise ValidationError("authoring requires a parent or HTML", field="html")
    if metadata_updates is not None and not isinstance(metadata_updates, Mapping):
        raise ValidationError(
            "metadata_updates must be an object", field="metadata_updates"
        )
    if metadata_updates == {}:
        raise ValidationError(
            "metadata_updates must contain an operation", field="metadata_updates"
        )

    patches = _parse_patches(metadata_updates)
    parent_by_id = (
        {}
        if normalized_parent is None
        else {block.id: block for block in normalized_parent.blocks}
    )

    if html is None:
        if normalized_parent is None:
            raise ValidationError(
                "metadata_updates requires a parent", field="metadata_updates"
            )
        _validate_targets(patches, set(parent_by_id), html_supplied=False)
        blocks = list(normalized_parent.blocks)
        for index, block in enumerate(blocks):
            patch = patches.get(block.id)
            if patch is not None:
                blocks[index] = _apply_patch(block, patch)
        return AuthoringResolution(
            normalize_document(replace(normalized_parent, blocks=tuple(blocks))), {}
        )

    inputs = parse_authoring_html(html)
    id_map: dict[str, str] = {}
    resolved_blocks: list[NovelBlock] = []
    token_to_formal: dict[str, str] = {}
    input_by_token: dict[str, AuthoringBlockInput] = {}
    for item in inputs:
        parent_block = parent_by_id.get(item.supplied_id or "")
        if item.supplied_id is None:
            formal_id = new_block_id()
        elif parent_block is not None:
            formal_id = parent_block.id
        else:
            formal_id = new_block_id()
            id_map[item.supplied_id] = formal_id
        if item.supplied_id is not None:
            token_to_formal[item.supplied_id] = formal_id
            input_by_token[item.supplied_id] = item
        resolved_blocks.append(_resolve_html_block(item, parent_block, formal_id))

    _validate_targets(patches, set(token_to_formal), html_supplied=True)
    for token, patch in patches.items():
        formal_id = token_to_formal[token]
        index = next(
            index
            for index, block in enumerate(resolved_blocks)
            if block.id == formal_id
        )
        _check_html_patch_conflicts(input_by_token[token], patch)
        resolved_blocks[index] = _apply_patch(resolved_blocks[index], patch)

    document = normalize_document(NovelDocument(blocks=tuple(resolved_blocks)))
    return AuthoringResolution(document, id_map)


def _resolve_html_block(
    item: AuthoringBlockInput,
    parent: NovelBlock | None,
    formal_id: str,
) -> NovelBlock:
    block_type = item.type_hint or (parent.type if parent is not None else "narration")
    attrs = item.attrs
    if block_type == "heading":
        heading_level = attrs.get(
            "heading_level",
            parent.attrs.heading_level if parent is not None else None,
        )
    else:
        heading_level = None
    return NovelBlock(
        id=formal_id,
        type=block_type,
        html=item.html,
        attrs=BlockAttrs(
            scene_id=attrs.get(
                "scene_id", parent.attrs.scene_id if parent is not None else None
            ),
            speaker_character_id=attrs.get(
                "speaker_character_id",
                parent.attrs.speaker_character_id if parent is not None else None,
            ),
            heading_level=heading_level,
        ),
        annotations=_resolve_annotations(item, parent),
    )


def _resolve_annotations(
    item: AuthoringBlockInput, parent: NovelBlock | None
) -> dict[str, JsonValue]:
    annotations = {} if parent is None else dict(parent.annotations)
    for key in item.remove_annotations:
        annotations.pop(key, None)
    annotations.update(item.annotations)
    return annotations


def _parse_patches(
    metadata_updates: Mapping[str, object] | None,
) -> dict[str, _MetadataPatch]:
    if metadata_updates is None:
        return {}
    patches: dict[str, _MetadataPatch] = {}
    for block_id, raw_patch in metadata_updates.items():
        if not isinstance(block_id, str) or not block_id:
            raise ValidationError("metadata target must be a non-empty string")
        if not isinstance(raw_patch, Mapping):
            raise ValidationError("metadata patch must be an object", field=block_id)
        if not set(raw_patch).issubset(_PATCH_NAMES):
            raise ValidationError(
                "metadata patch contains an unknown field", field=block_id
            )
        attrs = _parse_patch_attrs(raw_patch.get("attrs"))
        annotations = _parse_patch_annotations(raw_patch.get("annotations"))
        removals = _parse_removals(raw_patch.get("remove_annotations"))
        if set(annotations) & set(removals):
            raise ValidationError("annotation set/remove conflict", field=block_id)
        if not attrs and not annotations and not removals:
            raise ValidationError(
                "individual metadata patch cannot be empty", field=block_id
            )
        patches[block_id] = _MetadataPatch(attrs, annotations, removals)
    return patches


def _parse_patch_attrs(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValidationError("attrs must be an object")
    if not set(raw).issubset(_ATTR_NAMES):
        raise ValidationError("attrs contains an unknown field")
    result: dict[str, object] = {}
    for name, value in raw.items():
        if name in {"scene_id", "speaker_character_id"}:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValidationError(
                    f"{name} must be a positive integer or null", field=name
                )
        elif value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3
        ):
            raise ValidationError(
                "heading_level must be an integer from 1 through 3", field=name
            )
        result[str(name)] = value
    return result


def _parse_patch_annotations(raw: object) -> dict[str, JsonValue]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValidationError("annotations must be an object")
    result: dict[str, JsonValue] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise ValidationError("annotation keys must be non-empty strings")
        result[key] = cast(JsonValue, value)
    return result


def _parse_removals(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValidationError("remove_annotations must be a non-empty string list")
    values = tuple(raw)
    if any(not isinstance(value, str) or not value for value in values):
        raise ValidationError("remove_annotations keys must be non-empty strings")
    if len(values) != len(set(values)):
        raise ValidationError("remove_annotations keys must be unique")
    return values


def _validate_targets(
    patches: Mapping[str, _MetadataPatch], allowed: set[str], *, html_supplied: bool
) -> None:
    for target in patches:
        if target not in allowed:
            reason = "snapshot" if html_supplied else "parent"
            raise ValidationError(
                f"metadata target is absent from {reason}", field=target
            )


def _check_html_patch_conflicts(
    item: AuthoringBlockInput, patch: _MetadataPatch
) -> None:
    for name, value in patch.attrs.items():
        if name in item.attrs and item.attrs[name] != value:
            raise ValidationError("HTML and metadata field conflict", field=name)
    for key, value in patch.annotations.items():
        if key in item.annotations and item.annotations[key] != value:
            raise ValidationError("HTML and metadata annotation conflict", field=key)
        if key in item.remove_annotations:
            raise ValidationError("annotation set/remove conflict", field=key)
    if set(item.remove_annotations) & set(patch.annotations):
        raise ValidationError("annotation set/remove conflict")


def _apply_patch(block: NovelBlock, patch: _MetadataPatch) -> NovelBlock:
    attrs = block.attrs
    if "heading_level" in patch.attrs:
        heading_level = patch.attrs["heading_level"]
        if block.type != "heading" and heading_level is not None:
            raise ValidationError(
                "non-heading blocks cannot have a heading_level", field="heading_level"
            )
        attrs = replace(attrs, heading_level=cast(int | None, heading_level))
    if "scene_id" in patch.attrs:
        attrs = replace(attrs, scene_id=cast(int | None, patch.attrs["scene_id"]))
    if "speaker_character_id" in patch.attrs:
        attrs = replace(
            attrs,
            speaker_character_id=cast(int | None, patch.attrs["speaker_character_id"]),
        )
    annotations = dict(block.annotations)
    for key in patch.remove_annotations:
        annotations.pop(key, None)
    annotations.update(patch.annotations)
    return replace(block, attrs=attrs, annotations=annotations)
