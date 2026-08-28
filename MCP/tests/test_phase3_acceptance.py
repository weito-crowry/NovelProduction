from __future__ import annotations

from pathlib import Path


def test_phase3_domain_acceptance_remains_in_core_and_api() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "CORE" / "tests" / "test_outline_service.py").is_file()
    assert (root / "API" / "tests" / "test_phase3_api.py").is_file()
