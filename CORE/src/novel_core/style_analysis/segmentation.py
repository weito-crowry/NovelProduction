from __future__ import annotations

import re
from dataclasses import dataclass

from novel_core.errors import ValidationError


@dataclass(frozen=True, slots=True)
class SentenceDraft:
    start_cp: int
    end_cp: int


@dataclass(frozen=True, slots=True)
class BlockDraft:
    paragraph_index: int
    block_type: str
    start_cp: int
    end_cp: int
    scene_index: int | None
    sentences: tuple[SentenceDraft, ...]


@dataclass(frozen=True, slots=True)
class SceneDraft:
    start_cp: int
    end_cp: int
    block_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class AutomaticStructureDraft:
    scenes: tuple[SceneDraft, ...]
    blocks: tuple[BlockDraft, ...]
    warnings: tuple[str, ...]


_HEADING_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百千万]+[章節話回]|序章|終章|序幕|終幕)"
)
_QUOTE_CLOSERS = frozenset("」』）】〕］〉》】〕〙〗")
_SENTENCE_ENDS = frozenset("。！？!?")


def build_automatic_structure(
    canonical_text: str, scene_break_offsets_cp: object
) -> AutomaticStructureDraft:
    if not isinstance(canonical_text, str):
        raise ValidationError("TEXT_INVALID")
    offsets = _validate_offsets(scene_break_offsets_cp, len(canonical_text))
    blocks: list[BlockDraft] = []
    warnings: list[str] = []
    for paragraph_index, (start_cp, end_cp) in enumerate(
        _paragraph_spans(canonical_text), start=1
    ):
        paragraph = canonical_text[start_cp:end_cp]
        blocks.extend(
            _paragraph_blocks(
                paragraph,
                paragraph_index=paragraph_index,
                offset=start_cp,
                warnings=warnings,
            )
        )

    usable_boundary_offsets = {
        block.end_cp
        for index, block in enumerate(blocks)
        if block.block_type != "separator"
        and any(
            next_block.block_type != "separator" for next_block in blocks[index + 1 :]
        )
        and block.end_cp in offsets
    }
    scenes: list[SceneDraft] = []
    current: list[int] = []
    for block_index, block in enumerate(blocks):
        if block.block_type == "separator":
            _append_scene(scenes, blocks, current)
            current = []
            continue
        if block.block_type == "heading" and current:
            _append_scene(scenes, blocks, current)
            current = []
        if current and blocks[current[-1]].end_cp in usable_boundary_offsets:
            _append_scene(scenes, blocks, current)
            current = []
        current.append(block_index)
        if block.end_cp in usable_boundary_offsets:
            _append_scene(scenes, blocks, current)
            current = []
    _append_scene(scenes, blocks, current)

    valid_boundaries = usable_boundary_offsets
    for offset in offsets:
        if offset not in valid_boundaries:
            warnings.append("scene_break_hint_not_on_block_boundary")

    scene_by_block: dict[int, int] = {}
    for scene_index, scene in enumerate(scenes):
        for block_index in scene.block_indexes:
            scene_by_block[block_index] = scene_index
    blocks = [
        BlockDraft(
            paragraph_index=block.paragraph_index,
            block_type=block.block_type,
            start_cp=block.start_cp,
            end_cp=block.end_cp,
            scene_index=scene_by_block.get(index),
            sentences=block.sentences,
        )
        for index, block in enumerate(blocks)
    ]
    return AutomaticStructureDraft(tuple(scenes), tuple(blocks), tuple(warnings))


def _validate_offsets(value: object, text_length: int) -> tuple[int, ...]:
    if not isinstance(value, list) or any(
        not isinstance(offset, int) or isinstance(offset, bool) for offset in value
    ):
        raise ValidationError("STRUCTURE_HINTS_INVALID")
    offsets = tuple(sorted(set(value)))
    if any(offset <= 0 or offset >= text_length for offset in offsets):
        raise ValidationError("STRUCTURE_HINTS_INVALID")
    return offsets


def _paragraph_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    start = 0
    while start <= len(text):
        separator = text.find("\n\n", start)
        end = len(text) if separator < 0 else separator
        if end > start:
            spans.append((start, end))
        if separator < 0:
            break
        start = separator + 2
    return tuple(spans)


def _paragraph_blocks(
    paragraph: str,
    *,
    paragraph_index: int,
    offset: int,
    warnings: list[str],
) -> list[BlockDraft]:
    if _HEADING_RE.match(paragraph):
        return [
            _block(
                paragraph_index, "heading", offset, offset + len(paragraph), paragraph
            )
        ]
    if _is_separator(paragraph):
        return [
            _block(
                paragraph_index, "separator", offset, offset + len(paragraph), paragraph
            )
        ]
    result: list[BlockDraft] = []
    cursor = 0
    dialogue_start: int | None = None
    depth = 0
    for index, character in enumerate(paragraph):
        if character == "「":
            if depth == 0:
                if index > cursor:
                    result.append(
                        _block(
                            paragraph_index,
                            "narration",
                            offset + cursor,
                            offset + index,
                            paragraph[cursor:index],
                        )
                    )
                dialogue_start = index
            depth += 1
        elif character == "」" and depth:
            depth -= 1
            if depth == 0 and dialogue_start is not None:
                result.append(
                    _block(
                        paragraph_index,
                        "dialogue",
                        offset + dialogue_start,
                        offset + index + 1,
                        paragraph[dialogue_start : index + 1],
                    )
                )
                cursor = index + 1
                dialogue_start = None
    if dialogue_start is not None:
        warnings.append("unmatched_dialogue_quote")
        result.append(
            _block(
                paragraph_index,
                "dialogue",
                offset + dialogue_start,
                offset + len(paragraph),
                paragraph[dialogue_start:],
            )
        )
        cursor = len(paragraph)
    if cursor < len(paragraph):
        result.append(
            _block(
                paragraph_index,
                "narration",
                offset + cursor,
                offset + len(paragraph),
                paragraph[cursor:],
            )
        )
    return result or [
        _block(paragraph_index, "unknown", offset, offset + len(paragraph), paragraph)
    ]


def _block(
    paragraph_index: int,
    block_type: str,
    start_cp: int,
    end_cp: int,
    text: str,
) -> BlockDraft:
    sentences = (
        _split_sentences(text, start_cp)
        if block_type in {"dialogue", "narration"}
        else ()
    )
    return BlockDraft(paragraph_index, block_type, start_cp, end_cp, None, sentences)


def _split_sentences(text: str, offset: int) -> tuple[SentenceDraft, ...]:
    result: list[SentenceDraft] = []
    start = 0
    for index, character in enumerate(text):
        if character not in _SENTENCE_ENDS:
            continue
        end = index + 1
        while end < len(text) and text[end] in _QUOTE_CLOSERS:
            end += 1
        result.append(SentenceDraft(offset + start, offset + end))
        start = end
    if start < len(text):
        result.append(SentenceDraft(offset + start, offset + len(text)))
    return tuple(result)


def _is_separator(paragraph: str) -> bool:
    return bool(paragraph) and not any(character.isalnum() for character in paragraph)


def _append_scene(
    scenes: list[SceneDraft], blocks: list[BlockDraft], block_indexes: list[int]
) -> None:
    if not block_indexes:
        return
    scenes.append(
        SceneDraft(
            start_cp=blocks[block_indexes[0]].start_cp,
            end_cp=blocks[block_indexes[-1]].end_cp,
            block_indexes=tuple(block_indexes),
        )
    )
