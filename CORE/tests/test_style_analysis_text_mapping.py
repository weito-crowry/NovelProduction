from __future__ import annotations

import pytest

from novel_core.errors import ValidationError
from novel_core.style_analysis.normalization import normalize_text
from novel_core.style_analysis.text_mapping import (
    TextMapSegment,
    map_canonical_span_to_raw,
    map_raw_boundary,
)


def test_raw_boundary_mapping_reports_unique_and_ambiguous_points() -> None:
    result = normalize_text("A  \nB", [])
    assert map_raw_boundary(result.segments, 0) == 0
    assert map_raw_boundary(result.segments, len(result.raw_text)) == 3
    assert map_raw_boundary(result.segments, 2) is None


def test_canonical_span_mapping_exposes_exact_flag() -> None:
    segments = (
        TextMapSegment(0, 1, 0, 1, "identity"),
        TextMapSegment(1, 3, 1, 1, "delete"),
        TextMapSegment(3, 4, 1, 2, "identity"),
    )
    exact = map_canonical_span_to_raw(segments, 0, 1)
    assert exact is not None
    assert (exact.raw_start, exact.raw_end, exact.exact) == (0, 1, True)
    mapped = map_canonical_span_to_raw(segments, 0, 2)
    assert mapped is not None and mapped.exact is False


def test_mapping_rejects_invalid_spans() -> None:
    with pytest.raises(ValidationError, match="TEXT_MAPPING_INVALID"):
        map_canonical_span_to_raw((), 2, 1)
