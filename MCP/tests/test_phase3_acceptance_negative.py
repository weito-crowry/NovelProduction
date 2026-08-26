from __future__ import annotations

from novel_mcp.phase3_acceptance_probes import safe_keys


def test_acceptance_probe_rejects_explicit_unsafe_payload() -> None:
    assert safe_keys({"participant": {"private_notes": "UNSAFE_SENTINEL"}}) is False
