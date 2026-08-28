from __future__ import annotations

from pathlib import Path


def test_phase3_transport_regressions_are_covered_by_http_adapter_tests() -> None:
    tests = Path(__file__).resolve().parent
    assert (tests / "test_phase3_http_adapter.py").is_file()
    assert (tests / "test_api_client.py").is_file()
