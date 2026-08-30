"""Typed values for the Canonical Document Schema v1."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

JsonPrimitive: TypeAlias = None | bool | int | float | str  # noqa: UP040
JsonValue: TypeAlias = (  # noqa: UP040
    JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
)

BlockType: TypeAlias = Literal[  # noqa: UP040
    "narration",
    "dialogue",
    "thought",
    "description",
    "quote",
    "heading",
    "separator",
    "note",
]

FORMAL_BLOCK_ID_PATTERN = re.compile(r"^blk_[0-9a-f]{32}$")


@dataclass(frozen=True, slots=True)
class BlockAttrs:
    """Strict structural metadata for one Canonical block."""

    scene_id: int | None = None
    speaker_character_id: int | None = None
    heading_level: int | None = None


@dataclass(frozen=True, slots=True)
class NovelBlock:
    """One ordered, flat Canonical Document block."""

    id: str
    type: BlockType
    html: str
    attrs: BlockAttrs = field(default_factory=BlockAttrs)
    annotations: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NovelDocument:
    """The complete self-contained Canonical Document."""

    schema_version: int = 1
    type: str = "novel_document"
    blocks: tuple[NovelBlock, ...] = ()


def is_formal_block_id(value: object) -> bool:
    """Return whether *value* is a Canonical formal block ID."""

    return (
        isinstance(value, str) and FORMAL_BLOCK_ID_PATTERN.fullmatch(value) is not None
    )
