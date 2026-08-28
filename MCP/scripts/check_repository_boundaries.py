from __future__ import annotations

import ast
from collections.abc import Collection
from pathlib import Path

EXPECTED_MCP_TOOL_COUNT = 55
API_FORBIDDEN_IMPORT_ROOTS = frozenset({"mcp", "novel_mcp"})
CORE_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"api", "fastapi", "mcp", "novel_api", "novel_mcp"}
)
DIRECT_SQL_METHODS = frozenset({"execute", "executemany", "executescript"})
API_SQLITE_ALLOWED_PATHS = frozenset(
    {
        "novel_api/errors.py",
        "novel_api/project_registry.py",
        "novel_api/serialization.py",
        "novel_api/service_container.py",
    }
)


def _python_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.glob("**/*.py")))


def _parsed_tree(path: Path, failures: list[str]) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        failures.append(f"{path}: cannot inspect invalid Python: {exc.msg}")
        return None


def _import_roots(tree: ast.Module) -> tuple[str, ...]:
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.append(node.module.partition(".")[0])
    return tuple(roots)


def _check_imports(
    paths: tuple[Path, ...],
    *,
    forbidden_roots: frozenset[str],
    layer_name: str,
    failures: list[str],
) -> None:
    for path in paths:
        tree = _parsed_tree(path, failures)
        if tree is None:
            continue
        for root in sorted(set(_import_roots(tree)) & forbidden_roots):
            failures.append(f"{path}: {layer_name} must not import {root}")


def _check_api_sqlite_imports(
    api_root: Path, paths: tuple[Path, ...], failures: list[str]
) -> None:
    for path in paths:
        tree = _parsed_tree(path, failures)
        if tree is None or "sqlite3" not in _import_roots(tree):
            continue
        relative_path = path.relative_to(api_root).as_posix()
        if relative_path not in API_SQLITE_ALLOWED_PATHS:
            failures.append(
                f"{path}: sqlite3 is restricted to API error/type/connection plumbing"
            )


def _check_api_route_sql(route_paths: tuple[Path, ...], failures: list[str]) -> None:
    for path in route_paths:
        tree = _parsed_tree(path, failures)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in DIRECT_SQL_METHODS
            ):
                failures.append(
                    f"{path}:{node.lineno}: "
                    "API routes must not perform direct SQL execution"
                )


def collect_failures(repo_root: Path, *, tool_names: Collection[str]) -> list[str]:
    failures: list[str] = []
    api_root = repo_root / "API" / "src"
    core_root = repo_root / "CORE" / "src"
    api_paths = _python_files(api_root)
    core_paths = _python_files(core_root)

    _check_imports(
        api_paths,
        forbidden_roots=API_FORBIDDEN_IMPORT_ROOTS,
        layer_name="API",
        failures=failures,
    )
    _check_imports(
        core_paths,
        forbidden_roots=CORE_FORBIDDEN_IMPORT_ROOTS,
        layer_name="CORE",
        failures=failures,
    )
    _check_api_sqlite_imports(api_root, api_paths, failures)
    _check_api_route_sql(_python_files(api_root / "novel_api" / "routes"), failures)

    migration_005_paths = sorted((repo_root / "CORE" / "migrations").glob("005*"))
    for path in migration_005_paths:
        failures.append(f"{path}: migration 005 is outside Phase B")
    if (repo_root / "MCP" / "migrations").is_dir():
        failures.append("MCP/migrations must remain absent; CORE owns migrations")

    tool_count = len(tool_names)
    if tool_count != EXPECTED_MCP_TOOL_COUNT:
        failures.append(
            f"MCP tool count is {tool_count}; expected {EXPECTED_MCP_TOOL_COUNT}"
        )
    return failures


def main() -> int:
    from novel_mcp.mcp_server import ALL_TOOL_NAMES

    repo_root = Path(__file__).resolve().parents[2]
    failures = collect_failures(repo_root, tool_names=ALL_TOOL_NAMES)
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print("repository boundary checks passed; MCP tool count: 55")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
