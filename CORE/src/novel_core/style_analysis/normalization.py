from __future__ import annotations

import difflib
import re
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


NORMALIZER_ID = "canonical-japanese-fiction"
NORMALIZER_VERSION = 1


def normalize_text(
    raw_text: str, scene_break_offsets_raw: object
) -> NormalizationResult:
    if not isinstance(raw_text, str):
        raise ValidationError("TEXT_INVALID")
    raw_offsets = _normalize_offsets(scene_break_offsets_raw, len(raw_text))
    canonical_text = _canonicalize(raw_text)
    segments = _build_segments(raw_text, canonical_text)
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


def _canonicalize(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    text = "".join(
        character for character in text if not _is_removed_control(character)
    )
    text = text.replace("\t", " ")
    lines = [line.rstrip(" ") for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = text.split("\n")
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _is_removed_control(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint == 0
        or 1 <= codepoint <= 8
        or 11 <= codepoint <= 12
        or 14 <= codepoint <= 31
        or codepoint == 127
    )


def _build_segments(raw_text: str, canonical_text: str) -> tuple[TextMapSegment, ...]:
    matcher = difflib.SequenceMatcher(a=raw_text, b=canonical_text, autojunk=False)
    result: list[TextMapSegment] = []
    for (
        tag,
        raw_start,
        raw_end,
        canonical_start,
        canonical_end,
    ) in matcher.get_opcodes():
        if tag == "equal":
            operation: NormalizationOperation = "identity"
        elif tag == "delete":
            operation = "delete"
        elif tag == "replace":
            operation = _replace_operation(
                raw_text[raw_start:raw_end],
                canonical_text[canonical_start:canonical_end],
            )
        else:
            raise ValidationError("TEXT_MAPPING_INVALID")
        if raw_start == raw_end and canonical_start == canonical_end:
            continue
        result.append(
            TextMapSegment(
                raw_start=raw_start,
                raw_end=raw_end,
                canonical_start=canonical_start,
                canonical_end=canonical_end,
                operation=operation,
            )
        )
    result = _collapse_newline_segments(result, raw_text, canonical_text)
    result = _coalesce_identity_segments(result)
    _validate_segments(result, len(raw_text), len(canonical_text))
    return tuple(result)


def _replace_operation(raw: str, canonical: str) -> NormalizationOperation:
    if not canonical:
        return "delete"
    if raw.count("\n") >= 3 and canonical == "\n\n":
        return "collapse"
    if "\r" in raw and canonical == "\n":
        return "collapse" if len(raw) > 1 else "replace"
    return "replace"


def _collapse_newline_segments(
    segments: list[TextMapSegment], raw_text: str, canonical_text: str
) -> list[TextMapSegment]:
    """Preserve the semantic ``collapse`` operation after sequence alignment.

    SequenceMatcher can express a long newline run as an identity followed by
    deletes. The persisted mapping still represents that whole normalization
    operation as one collapse segment.
    """
    boundaries = {
        boundary
        for match in re.finditer(r"(?:(?:\r\n)|\r|\n){3,}", raw_text)
        for boundary in (match.start(), match.end())
    }
    segments = _split_at_raw_boundaries(segments, boundaries)
    collapsed: list[TextMapSegment] = []
    consumed: set[int] = set()
    for match in re.finditer(r"(?:(?:\r\n)|\r|\n){3,}", raw_text):
        selected = [
            (index, segment)
            for index, segment in enumerate(segments)
            if segment.raw_start >= match.start() and segment.raw_end <= match.end()
        ]
        if not selected:
            continue
        canonical_start = min(segment.canonical_start for _, segment in selected)
        canonical_end = max(segment.canonical_end for _, segment in selected)
        if canonical_text[canonical_start:canonical_end] != "\n\n":
            continue
        first_index, first = selected[0]
        last_index, last = selected[-1]
        collapsed.append(
            TextMapSegment(
                raw_start=first.raw_start,
                raw_end=last.raw_end,
                canonical_start=canonical_start,
                canonical_end=canonical_end,
                operation="collapse",
            )
        )
        consumed.update(index for index, _ in selected)
    if not consumed:
        return segments
    result: list[TextMapSegment] = []
    replacements = {segment.raw_start: segment for segment in collapsed}
    for index, segment in enumerate(segments):
        if index in consumed:
            replacement = replacements.get(segment.raw_start)
            if replacement is not None:
                result.append(replacement)
            continue
        result.append(segment)
    return result


def _split_at_raw_boundaries(
    segments: list[TextMapSegment], boundaries: set[int]
) -> list[TextMapSegment]:
    result: list[TextMapSegment] = []
    for segment in segments:
        cuts = sorted(
            boundary
            for boundary in boundaries
            if segment.raw_start < boundary < segment.raw_end
        )
        starts = [segment.raw_start, *cuts]
        ends = [*cuts, segment.raw_end]
        raw_length = segment.raw_end - segment.raw_start
        canonical_length = segment.canonical_end - segment.canonical_start
        for start, end in zip(starts, ends, strict=True):
            start_ratio = (start - segment.raw_start) / raw_length
            end_ratio = (end - segment.raw_start) / raw_length
            canonical_start = segment.canonical_start + round(
                canonical_length * start_ratio
            )
            canonical_end = segment.canonical_start + round(
                canonical_length * end_ratio
            )
            result.append(
                TextMapSegment(
                    raw_start=start,
                    raw_end=end,
                    canonical_start=canonical_start,
                    canonical_end=canonical_end,
                    operation=segment.operation,
                )
            )
    return result


def _coalesce_identity_segments(
    segments: list[TextMapSegment],
) -> list[TextMapSegment]:
    result: list[TextMapSegment] = []
    for segment in segments:
        if (
            result
            and result[-1].operation == "identity"
            and segment.operation == "identity"
            and result[-1].raw_end == segment.raw_start
            and result[-1].canonical_end == segment.canonical_start
        ):
            previous = result[-1]
            result[-1] = TextMapSegment(
                raw_start=previous.raw_start,
                raw_end=segment.raw_end,
                canonical_start=previous.canonical_start,
                canonical_end=segment.canonical_end,
                operation="identity",
            )
        else:
            result.append(segment)
    return result


def _validate_segments(
    segments: list[TextMapSegment], raw_length: int, canonical_length: int
) -> None:
    previous_raw_end = 0
    previous_canonical_end = 0
    for segment in segments:
        if (
            segment.raw_start < previous_raw_end
            or segment.canonical_start < previous_canonical_end
        ):
            raise ValidationError("TEXT_MAPPING_INVALID")
        if (
            segment.raw_end < segment.raw_start
            or segment.canonical_end < segment.canonical_start
        ):
            raise ValidationError("TEXT_MAPPING_INVALID")
        if (
            segment.raw_start == segment.raw_end
            and segment.canonical_start == segment.canonical_end
        ):
            raise ValidationError("TEXT_MAPPING_INVALID")
        if segment.raw_end > raw_length or segment.canonical_end > canonical_length:
            raise ValidationError("TEXT_MAPPING_INVALID")
        previous_raw_end = segment.raw_end
        previous_canonical_end = segment.canonical_end
