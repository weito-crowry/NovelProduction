from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_script(relative_path: str, module_name: str) -> ModuleType:
    script_path = REPOSITORY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOURCE_SIZE = _load_script("MCP/scripts/check_source_size.py", "check_source_size")


def _boundary_checker() -> ModuleType:
    return _load_script(
        "MCP/scripts/check_repository_boundaries.py",
        "check_repository_boundaries",
    )


def _write_python(repo_root: Path, relative_path: str, source: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


@pytest.mark.parametrize(
    ("relative_root", "line_count"),
    [
        ("CORE/src", 601),
        ("CORE/tests", 801),
        ("API/src", 601),
        ("API/tests", 801),
        ("MCP/src", 601),
        ("MCP/tests", 801),
    ],
)
def test_source_size_inspects_each_authorized_root(
    tmp_path: Path, relative_root: str, line_count: int
) -> None:
    oversized = tmp_path / relative_root / "oversized.py"
    oversized.parent.mkdir(parents=True)
    oversized.write_text("line\n" * line_count, encoding="utf-8")

    failures = SOURCE_SIZE.collect_failures(tmp_path)

    assert len(failures) == 1
    assert str(oversized) in failures[0]


def test_source_size_ignores_python_outside_authorized_roots(tmp_path: Path) -> None:
    outside = tmp_path / "WEBUI" / "src" / "oversized.py"
    outside.parent.mkdir(parents=True)
    outside.write_text("line\n" * 1000, encoding="utf-8")

    assert SOURCE_SIZE.collect_failures(tmp_path) == []


@pytest.mark.parametrize("module_name", ["novel_mcp", "mcp"])
def test_boundary_checker_rejects_api_imports_from_mcp(
    tmp_path: Path, module_name: str
) -> None:
    _write_python(
        tmp_path,
        "API/src/novel_api/client.py",
        f"from {module_name}.server import call\n",
    )

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("API must not import" in failure for failure in failures)


@pytest.mark.parametrize("module_name", ["novel_api", "fastapi", "novel_mcp", "mcp"])
def test_boundary_checker_rejects_core_imports_from_outer_layers(
    tmp_path: Path, module_name: str
) -> None:
    _write_python(
        tmp_path,
        "CORE/src/novel_core/forbidden.py",
        f"import {module_name}\n",
    )

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("CORE must not import" in failure for failure in failures)


@pytest.mark.parametrize("method_name", ["execute", "executemany", "executescript"])
def test_boundary_checker_rejects_direct_sql_in_api_routes(
    tmp_path: Path, method_name: str
) -> None:
    _write_python(
        tmp_path,
        "API/src/novel_api/routes/forbidden.py",
        f'def route(connection):\n    connection.{method_name}("SELECT 1")\n',
    )

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("direct SQL execution" in failure for failure in failures)


def test_boundary_checker_rejects_sqlite_outside_api_plumbing(tmp_path: Path) -> None:
    _write_python(
        tmp_path,
        "API/src/novel_api/routes/forbidden.py",
        "import sqlite3\n",
    )

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("sqlite3 is restricted" in failure for failure in failures)


def test_boundary_checker_rejects_migration_005(tmp_path: Path) -> None:
    migration = tmp_path / "CORE" / "migrations" / "005_structured_drafts.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text("SELECT 1;\n", encoding="utf-8")

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("migration 005" in failure for failure in failures)


def test_boundary_checker_rejects_mcp_migration_ownership(tmp_path: Path) -> None:
    (tmp_path / "MCP" / "migrations").mkdir(parents=True)

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("MCP/migrations" in failure for failure in failures)


@pytest.mark.parametrize("tool_count", [54, 56])
def test_boundary_checker_rejects_mcp_tool_count_drift(
    tmp_path: Path, tool_count: int
) -> None:
    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(tool_count))
    )

    assert failures == [f"MCP tool count is {tool_count}; expected 59"]


def test_boundary_checker_accepts_current_layering_contract(tmp_path: Path) -> None:
    _write_python(
        tmp_path,
        "API/src/novel_api/routes/work.py",
        "from novel_core.services.work_service import WorkService\n",
    )
    _write_python(
        tmp_path,
        "CORE/src/novel_core/services/work_service.py",
        "from novel_core.models.work import Work\n",
    )
    _write_python(tmp_path, "API/src/novel_api/errors.py", "import sqlite3\n")

    assert (
        _boundary_checker().collect_failures(
            tmp_path, tool_names=tuple(str(index) for index in range(59))
        )
        == []
    )


@pytest.mark.parametrize(
    "module_name", ["novel_core", "sqlite3", "novel_api", "fastapi"]
)
def test_boundary_checker_rejects_forbidden_mcp_runtime_imports(
    tmp_path: Path, module_name: str
) -> None:
    _write_python(tmp_path, "MCP/src/novel_mcp/forbidden.py", f"import {module_name}\n")

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("MCP must not import" in failure for failure in failures)


def test_boundary_checker_rejects_mcp_runtime_dependencies(tmp_path: Path) -> None:
    (tmp_path / "MCP").mkdir()
    (tmp_path / "MCP" / "pyproject.toml").write_text(
        '[project]\ndependencies = ["novel-production-core"]\n', encoding="utf-8"
    )

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("MCP must not depend" in failure for failure in failures)


def test_boundary_checker_rejects_project_selection_state(tmp_path: Path) -> None:
    _write_python(
        tmp_path,
        "MCP/src/novel_mcp/forbidden.py",
        "project_select = 'not allowed'\n",
    )

    failures = _boundary_checker().collect_failures(
        tmp_path, tool_names=tuple(str(index) for index in range(59))
    )

    assert any("project_select is forbidden" in failure for failure in failures)


def test_boundary_checker_rejects_missing_required_project_id(tmp_path: Path) -> None:
    failures = _boundary_checker().collect_failures(
        tmp_path,
        tool_names=("work_get",),
        required_project_id_tools=(),
    )

    assert failures == [
        "MCP tools missing required project_id: work_get",
        "MCP tool count is 1; expected 59",
    ]
