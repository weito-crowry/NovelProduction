from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from novel_core.errors import ValidationError

NormalizationOperation = Literal["identity", "replace", "delete", "collapse"]


@dataclass(frozen=True, slots=True)
class TextMapSegment:
    raw_start: int
    raw_end: int
    canonical_start: int
    canonical_end: int
    operation: NormalizationOperation


@dataclass(frozen=True, slots=True)
class CanonicalSpanMapping:
    raw_start: int
    raw_end: int
    exact: bool


def map_raw_boundary(
    segments: tuple[TextMapSegment, ...], raw_offset: int
) -> int | None:
    candidates: set[int] = set()
    for segment in segments:
        if raw_offset == segment.raw_start:
            candidates.add(segment.canonical_start)
        if raw_offset == segment.raw_end:
            candidates.add(segment.canonical_end)
        if (
            segment.operation == "identity"
            and segment.raw_start < raw_offset < segment.raw_end
        ):
            candidates.add(segment.canonical_start + raw_offset - segment.raw_start)
    return next(iter(candidates)) if len(candidates) == 1 else None


def map_canonical_span_to_raw(
    segments: tuple[TextMapSegment, ...], canonical_start: int, canonical_end: int
) -> CanonicalSpanMapping | None:
    if canonical_start < 0 or canonical_end < canonical_start:
        raise ValidationError("TEXT_MAPPING_INVALID")
    overlapping = [
        segment
        for segment in segments
        if segment.canonical_start < canonical_end
        and segment.canonical_end > canonical_start
    ]
    if not overlapping:
        return None
    raw_bounds = [
        (
            max(canonical_start, segment.canonical_start),
            min(canonical_end, segment.canonical_end),
            segment,
        )
        for segment in overlapping
    ]
    raw_start = min(
        segment.raw_start
        if segment.operation != "identity"
        else segment.raw_start + start - segment.canonical_start
        for start, _, segment in raw_bounds
    )
    raw_end = max(
        segment.raw_end
        if segment.operation != "identity"
        else segment.raw_start + end - segment.canonical_start
        for _, end, segment in raw_bounds
    )
    covering = [
        segment
        for segment in segments
        if segment.raw_start < raw_end and segment.raw_end > raw_start
    ]
    return CanonicalSpanMapping(
        raw_start=raw_start,
        raw_end=raw_end,
        exact=all(
            segment.operation == "identity"
            and segment.raw_end - segment.raw_start
            == segment.canonical_end - segment.canonical_start
            for segment in covering
        ),
    )
