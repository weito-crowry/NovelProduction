from __future__ import annotations

from pathlib import Path


def test_development_foundation_files_and_constraints_exist() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    mcp_root = repo_root / "MCP"

    assert (repo_root / ".editorconfig").read_text(encoding="utf-8").strip()
    assert (repo_root / ".python-version").read_text(encoding="utf-8").strip() == "3.13"
    assert (repo_root / ".github" / "workflows" / "mcp-ci.yml").is_file()
    assert (mcp_root / ".pre-commit-config.yaml").is_file()
    assert (mcp_root / "scripts" / "check_source_size.py").is_file()

    pyproject_text = (mcp_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in pyproject_text
    assert '"mcp>=2.0,<3.0"' in pyproject_text


def test_development_foundation_enforces_phase1_coverage_and_ruff_rules() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    mcp_root = repo_root / "MCP"

    pyproject_text = (mcp_root / "pyproject.toml").read_text(encoding="utf-8")
    workflow_text = (repo_root / ".github" / "workflows" / "mcp-ci.yml").read_text(
        encoding="utf-8"
    )

    assert "fail_under = 80" in pyproject_text
    assert "show_missing = true" in pyproject_text
    assert '"UP"' in pyproject_text
    assert '"B"' in pyproject_text
    assert (
        "uv run pytest --cov=src/novel_mcp --cov-report=term-missing" in workflow_text
    )
