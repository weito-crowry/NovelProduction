import pytest

from novel_core.style_analysis.fingerprints import (
    canonical_json_bytes,
    fingerprint_json,
)


def test_fingerprint_ignores_object_key_order() -> None:
    assert fingerprint_json({"b": 2, "a": 1}) == fingerprint_json({"a": 1, "b": 2})


def test_fingerprint_uses_utf8_without_ascii_escaping() -> None:
    assert canonical_json_bytes({"text": "雪"}) == '{"text":"雪"}'.encode()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_fingerprint_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError):
        fingerprint_json({"value": value})
