from __future__ import annotations

import ast
from collections.abc import Collection
from pathlib import Path

EXPECTED_MCP_TOOL_COUNT = 59
API_FORBIDDEN_IMPORT_ROOTS = frozenset({"mcp", "novel_mcp"})
CORE_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"api", "fastapi", "mcp", "novel_api", "novel_mcp"}
)
MCP_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"novel_core", "sqlite3", "novel_api", "fastapi"}
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


def _check_mcp_dependencies(repo_root: Path, failures: list[str]) -> None:
    pyproject = repo_root / "MCP" / "pyproject.toml"
    if not pyproject.is_file():
        return
    text = pyproject.read_text(encoding="utf-8")
    if "novel-production-core" in text or "novel-production-api" in text:
        failures.append(f"{pyproject}: MCP must not depend on CORE or API")
    if '"httpx>=0.28,<1.0"' not in text:
        failures.append(f"{pyproject}: MCP must declare the httpx runtime dependency")


def _check_mcp_project_state(
    mcp_paths: tuple[Path, ...],
    *,
    tool_names: Collection[str],
    required_project_id_tools: Collection[str] | None,
    failures: list[str],
) -> None:
    for path in mcp_paths:
        if "project_select" in path.read_text(encoding="utf-8"):
            failures.append(f"{path}: project_select is forbidden")
    if required_project_id_tools is None:
        return
    expected = set(tool_names) - {
        "project_list",
        "project_get",
        "project_create",
        "project_update",
    }
    missing = sorted(expected - set(required_project_id_tools))
    if missing:
        failures.append("MCP tools missing required project_id: " + ", ".join(missing))


def _mapping_keys(path: Path, variable_name: str) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == variable_name
            for target in node.targets
        ) or not isinstance(node.value, ast.Dict):
            continue
        return frozenset(
            key.value
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        )
    return frozenset()


def _static_mcp_inventory(
    mcp_root: Path,
) -> tuple[dict[str, frozenset[str]], set[str]]:
    groups = {
        "project": ("project_tool_descriptions.py", "PROJECT_TOOL_DESCRIPTIONS"),
        "phase1": ("tool_descriptions.py", "TOOL_DESCRIPTIONS"),
        "phase2": ("phase2_tool_descriptions.py", "PHASE2_TOOL_DESCRIPTIONS"),
        "phase3": ("phase3_tool_descriptions.py", "PHASE3_TOOL_DESCRIPTIONS"),
    }
    description_root = mcp_root / "src" / "novel_mcp"
    inventories = {
        name: _mapping_keys(description_root / filename, variable_name)
        for name, (filename, variable_name) in groups.items()
    }
    required: set[str] = set()
    tool_roots = {
        "phase1": "phase1_tools.py",
        "phase2": "phase2_tools.py",
        "phase3": "phase3_tools.py",
    }
    for group_name, filename in tool_roots.items():
        tree = ast.parse((description_root / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if node.name not in inventories[group_name]:
                continue
            positional = [*node.args.posonlyargs, *node.args.args]
            required_positionals = len(positional) - len(node.args.defaults)
            if (
                positional
                and positional[0].arg == "project_id"
                and required_positionals
            ):
                required.add(node.name)
    return inventories, required


def collect_failures(
    repo_root: Path,
    *,
    tool_names: Collection[str],
    required_project_id_tools: Collection[str] | None = None,
) -> list[str]:
    failures: list[str] = []
    api_root = repo_root / "API" / "src"
    core_root = repo_root / "CORE" / "src"
    api_paths = _python_files(api_root)
    core_paths = _python_files(core_root)
    mcp_paths = _python_files(repo_root / "MCP" / "src")

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
    _check_imports(
        mcp_paths,
        forbidden_roots=MCP_FORBIDDEN_IMPORT_ROOTS,
        layer_name="MCP",
        failures=failures,
    )
    _check_mcp_dependencies(repo_root, failures)
    _check_mcp_project_state(
        mcp_paths,
        tool_names=tool_names,
        required_project_id_tools=required_project_id_tools,
        failures=failures,
    )
    _check_api_sqlite_imports(api_root, api_paths, failures)
    _check_api_route_sql(_python_files(api_root / "novel_api" / "routes"), failures)

    if (repo_root / "MCP" / "migrations").is_dir():
        failures.append("MCP/migrations must remain absent; CORE owns migrations")

    tool_count = len(tool_names)
    if tool_count != EXPECTED_MCP_TOOL_COUNT:
        failures.append(
            f"MCP tool count is {tool_count}; expected {EXPECTED_MCP_TOOL_COUNT}"
        )
    return failures


def main() -> int:
    import asyncio
    import sys

    mcp_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(mcp_root / "src"))
    repo_root = Path(__file__).resolve().parents[2]
    try:
        from novel_mcp.config import McpSettings
        from novel_mcp.mcp_server import (
            ALL_TOOL_NAMES,
            PHASE1_TOOL_NAMES,
            PHASE2_TOOL_NAMES,
            PHASE3_TOOL_NAMES,
            PROJECT_TOOL_NAMES,
            create_server,
        )
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("novel_mcp"):
            raise
        group_names, required_project_id_tools = _static_mcp_inventory(mcp_root)
        all_tool_names = frozenset().union(*group_names.values())
        required_project_id_tools.update({"project_get", "project_update"})
    else:

        async def inspect_server() -> set[str]:
            server = create_server(McpSettings("http://127.0.0.1:8765"))
            try:
                tools = await server.list_tools()
                return {
                    tool.name
                    for tool in tools
                    if "project_id" in tool.input_schema.get("required", [])
                }
            finally:
                await server.aclose()

        required_project_id_tools = asyncio.run(inspect_server())
        all_tool_names = ALL_TOOL_NAMES
        group_names = {
            "project": PROJECT_TOOL_NAMES,
            "phase1": PHASE1_TOOL_NAMES,
            "phase2": PHASE2_TOOL_NAMES,
            "phase3": PHASE3_TOOL_NAMES,
        }
    expected_required_project_id_tools = set(all_tool_names) - {
        "project_list",
        "project_create",
    }
    inventory_failures = []
    missing_project_id = sorted(
        expected_required_project_id_tools - required_project_id_tools
    )
    if missing_project_id:
        inventory_failures.append(
            "MCP tools missing required project_id: " + ", ".join(missing_project_id)
        )
    expected_group_counts = {
        "project": (group_names["project"], 4),
        "phase1": (group_names["phase1"], 23),
        "phase2": (group_names["phase2"], 27),
        "phase3": (group_names["phase3"], 5),
    }
    for group_name, (names, expected_count) in expected_group_counts.items():
        if len(names) != expected_count:
            inventory_failures.append(
                f"MCP {group_name} tool count is {len(names)}; "
                f"expected {expected_count}"
            )
    failures = collect_failures(
        repo_root,
        tool_names=all_tool_names,
        required_project_id_tools=required_project_id_tools,
    )
    failures.extend(inventory_failures)
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print("repository boundary checks passed; MCP tool count: 59")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
