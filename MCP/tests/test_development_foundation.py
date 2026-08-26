from __future__ import annotations

import re
from pathlib import Path


def test_development_foundation_files_and_constraints_exist() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    mcp_root = repo_root / "MCP"

    assert (repo_root / ".editorconfig").read_text(encoding="utf-8").strip()
    assert (repo_root / ".python-version").read_text(encoding="utf-8").strip() == "3.13"
    assert (repo_root / ".github" / "workflows" / "mcp-ci.yml").is_file()
    assert (mcp_root / ".pre-commit-config.yaml").is_file()
    assert (mcp_root / "scripts" / "check_source_size.py").is_file()
    migrations = sorted(path.name for path in (mcp_root / "migrations").glob("*.sql"))
    assert migrations == ["001_initial.sql", "002_search.sql", "003_narrative.sql"]

    pyproject_text = (mcp_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in pyproject_text
    assert '"mcp>=2.0,<3.0"' in pyproject_text
    assert "rev: v0.16.4" in (mcp_root / ".pre-commit-config.yaml").read_text(
        encoding="utf-8"
    )


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


def test_services_and_cli_contain_no_raw_sql_statements() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "novel_mcp"
    source_paths = sorted((source_root / "services").glob("*.py")) + [
        source_root / "cli.py"
    ]
    sql_tokens = re.compile(
        r"\b(?:SELECT|INSERT|UPDATE|DELETE|BEGIN|COMMIT|ROLLBACK)\b"
    )

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        assert sql_tokens.search(source) is None, source_path.name
