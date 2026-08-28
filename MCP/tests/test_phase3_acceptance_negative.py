from __future__ import annotations

from pathlib import Path


def test_phase3_db_acceptance_helpers_are_not_mcp_runtime_modules() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "novel_mcp"
    assert not (source / "phase3_acceptance.py").exists()
    assert not (source / "phase3_acceptance_probes.py").exists()
