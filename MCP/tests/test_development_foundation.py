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
