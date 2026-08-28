from __future__ import annotations

from pathlib import Path

from novel_mcp.mcp_server import parser


def test_mcp_no_longer_exposes_a_direct_database_initializer() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert "novel-init" not in pyproject.read_text(encoding="utf-8")


def test_mcp_runtime_parser_accepts_only_api_url() -> None:
    args = parser().parse_args(["--api-url", "http://127.0.0.1:9999"])
    assert args.api_url == "http://127.0.0.1:9999"
