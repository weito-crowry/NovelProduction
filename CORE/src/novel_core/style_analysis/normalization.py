from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from novel_core.errors import ValidationError
from novel_core.style_analysis.text_mapping import (
    NormalizationOperation,
    TextMapSegment,
    map_raw_boundary,
)


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    raw_text: str
    canonical_text: str
    segments: tuple[TextMapSegment, ...]
    scene_break_offsets_cp: tuple[int, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Piece:
    text: str
    raw_start: int
    raw_end: int
    operation: NormalizationOperation


NORMALIZER_ID = "canonical-japanese-fiction"
NORMALIZER_VERSION = 1
MAX_TEXT_CODE_POINTS = 2_000_000


def normalize_text(
    raw_text: str, scene_break_offsets_raw: object
) -> NormalizationResult:
    if not isinstance(raw_text, str):
        raise ValidationError("TEXT_INVALID")
    if len(raw_text) > MAX_TEXT_CODE_POINTS:
        raise ValidationError("TEXT_TOO_LARGE")
    raw_offsets = _normalize_offsets(scene_break_offsets_raw, len(raw_text))
    pieces = _normalize_pieces(raw_text)
    canonical_text = "".join(piece.text for piece in pieces if piece.text)
    if not canonical_text:
        raise ValidationError("TEXT_EMPTY")
    segments = _segments_from_pieces(pieces)
    mapped: list[int] = []
    warnings: list[str] = []
    for offset in raw_offsets:
        canonical_offset = map_raw_boundary(segments, offset)
        if canonical_offset is None:
            warnings.append("scene_break_hint_unmappable")
            continue
        if 0 < canonical_offset < len(canonical_text):
            mapped.append(canonical_offset)
        else:
            warnings.append("scene_break_hint_unmappable")
    return NormalizationResult(
        raw_text=raw_text,
        canonical_text=canonical_text,
        segments=segments,
        scene_break_offsets_cp=tuple(sorted(set(mapped))),
        warnings=tuple(warnings),
    )


def _normalize_offsets(value: object, text_length: int) -> tuple[int, ...]:
    if not isinstance(value, list) or any(
        not isinstance(offset, int) or isinstance(offset, bool) for offset in value
    ):
        raise ValidationError("STRUCTURE_HINTS_INVALID")
    offsets = tuple(sorted(set(value)))
    if any(offset < 0 or offset > text_length for offset in offsets):
        raise ValidationError("STRUCTURE_HINTS_INVALID")
    return offsets


def _normalize_pieces(raw_text: str) -> list[_Piece]:
    pieces = [
        _Piece(character, index, index + 1, "identity")
        for index, character in enumerate(raw_text)
    ]
    if pieces and pieces[0].text == "\ufeff":
        pieces[0] = _Piece("", pieces[0].raw_start, pieces[0].raw_end, "delete")
    pieces = _normalize_line_endings(pieces)
    pieces = _normalize_nfc(pieces)
    pieces = [
        _Piece(
            "" if _is_removed_control(piece.text) else piece.text,
            piece.raw_start,
            piece.raw_end,
            "delete" if _is_removed_control(piece.text) else piece.operation,
        )
        for piece in pieces
    ]
    pieces = [
        _Piece(
            " " if piece.text == "\t" else piece.text,
            piece.raw_start,
            piece.raw_end,
            "replace" if piece.text == "\t" else piece.operation,
        )
        for piece in pieces
    ]
    pieces = _remove_line_end_spaces(pieces)
    pieces = _collapse_blank_lines(pieces)
    return _trim_blank_lines(pieces)


def _normalize_line_endings(pieces: list[_Piece]) -> list[_Piece]:
    result: list[_Piece] = []
    index = 0
    while index < len(pieces):
        piece = pieces[index]
        if (
            piece.text == "\r"
            and index + 1 < len(pieces)
            and pieces[index + 1].text == "\n"
        ):
            following = pieces[index + 1]
            result.append(_Piece("\n", piece.raw_start, following.raw_end, "collapse"))
            index += 2
        elif piece.text == "\r":
            result.append(_Piece("\n", piece.raw_start, piece.raw_end, "replace"))
            index += 1
        else:
            result.append(piece)
            index += 1
    return result


def _normalize_nfc(pieces: list[_Piece]) -> list[_Piece]:
    result: list[_Piece] = []
    index = 0
    while index < len(pieces):
        piece = pieces[index]
        if not piece.text:
            result.append(piece)
            index += 1
            continue
        group = [piece]
        next_index = index + 1
        while next_index < len(pieces):
            next_piece = pieces[next_index]
            if not next_piece.text or not unicodedata.combining(next_piece.text[0]):
                break
            group.append(next_piece)
            next_index += 1
        source = "".join(item.text for item in group)
        normalized = unicodedata.normalize("NFC", source)
        if normalized == source:
            result.extend(group)
        else:
            result.append(
                _Piece(
                    normalized,
                    group[0].raw_start,
                    group[-1].raw_end,
                    "replace",
                )
            )
        index = next_index
    return result


def _is_removed_control(value: str) -> bool:
    if len(value) != 1:
        return False
    codepoint = ord(value)
    return (
        codepoint == 0
        or 1 <= codepoint <= 8
        or 11 <= codepoint <= 12
        or 14 <= codepoint <= 31
        or codepoint == 127
    )


def _remove_line_end_spaces(pieces: list[_Piece]) -> list[_Piece]:
    result = list(pieces)
    for index, piece in enumerate(result):
        if piece.text != " ":
            continue
        next_index = index + 1
        while next_index < len(result) and result[next_index].text == " ":
            next_index += 1
        next_text = result[next_index].text if next_index < len(result) else ""
        if next_text in {"", "\n"}:
            result[index] = _Piece("", piece.raw_start, piece.raw_end, "delete")
    return result


def _collapse_blank_lines(pieces: list[_Piece]) -> list[_Piece]:
    visible = [index for index, piece in enumerate(pieces) if piece.text]
    index = 0
    while index < len(visible):
        if pieces[visible[index]].text != "\n":
            index += 1
            continue
        end = index
        while end + 1 < len(visible) and visible[end + 1] == visible[end] + 1:
            if pieces[visible[end + 1]].text != "\n":
                break
            end += 1
        if end - index + 1 >= 3:
            first = visible[index]
            last = visible[end]
            replacement = _Piece(
                "\n\n", pieces[first].raw_start, pieces[last].raw_end, "collapse"
            )
            pieces = pieces[:first] + [replacement] + pieces[last + 1 :]
            visible = [idx for idx, piece in enumerate(pieces) if piece.text]
            index = 0
            continue
        index = end + 1
    return pieces


def _trim_blank_lines(pieces: list[_Piece]) -> list[_Piece]:
    result = list(pieces)
    while True:
        visible = [index for index, piece in enumerate(result) if piece.text]
        if not visible or result[visible[0]].text != "\n":
            break
        index = visible[0]
        piece = result[index]
        result[index] = _Piece("", piece.raw_start, piece.raw_end, "delete")
    while True:
        visible = [index for index, piece in enumerate(result) if piece.text]
        if not visible or result[visible[-1]].text != "\n":
            break
        index = visible[-1]
        piece = result[index]
        result[index] = _Piece("", piece.raw_start, piece.raw_end, "delete")
    return result


def _segments_from_pieces(pieces: list[_Piece]) -> tuple[TextMapSegment, ...]:
    segments: list[TextMapSegment] = []
    canonical_offset = 0
    for piece in pieces:
        canonical_end = canonical_offset + len(piece.text)
        operation: NormalizationOperation = piece.operation if piece.text else "delete"
        segment = TextMapSegment(
            piece.raw_start,
            piece.raw_end,
            canonical_offset,
            canonical_end,
            operation,
        )
        if (
            segments
            and segments[-1].operation == segment.operation
            and segments[-1].raw_end == segment.raw_start
            and segments[-1].canonical_end == segment.canonical_start
        ):
            previous = segments[-1]
            segments[-1] = TextMapSegment(
                previous.raw_start,
                segment.raw_end,
                previous.canonical_start,
                segment.canonical_end,
                segment.operation,
            )
        else:
            segments.append(segment)
        canonical_offset = canonical_end
    return tuple(segments)
