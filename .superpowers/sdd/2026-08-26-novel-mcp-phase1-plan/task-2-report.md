# Task 2 Report

## Scope

Implemented Task 2 in `C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation` on branch `codex/phase1-mcp-foundation`:

- explicit work metadata read/update support
- explicit `novel-init` initialization path
- optimistic concurrency with `expected_version`
- non-empty title validation
- no implicit work creation during ordinary database open

## Files Changed

- Modified: `MCP/pyproject.toml`
- Modified: `MCP/src/novel_mcp/errors.py`
- Added: `MCP/src/novel_mcp/cli.py`
- Added: `MCP/src/novel_mcp/repositories/__init__.py`
- Added: `MCP/src/novel_mcp/repositories/work_repository.py`
- Added: `MCP/src/novel_mcp/services/__init__.py`
- Added: `MCP/src/novel_mcp/services/work_service.py`
- Added: `MCP/tests/test_work_service.py`
- Added: `MCP/tests/test_novel_init.py`

## Red-Green Evidence

### Red

1. Initial brief-required command with system Python:

```powershell
Set-Location 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation'
$env:PYTHONPATH = 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation/MCP/src'
python -m pytest MCP/tests/test_work_service.py MCP/tests/test_novel_init.py -q
```

Output:

```text
C:\Program Files\Python313\python.exe: No module named pytest
```

This was an environment gap, not useful red-phase evidence for the feature.

2. Repo-managed red run:

```powershell
Set-Location 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation'
uv run --directory MCP python -m pytest tests/test_work_service.py tests/test_novel_init.py -q
```

Output:

```text
ERROR tests/test_work_service.py
E   ModuleNotFoundError: No module named 'novel_mcp.services'
ERROR tests/test_novel_init.py
E   ModuleNotFoundError: No module named 'novel_mcp.cli'
```

This is the expected failing state before implementation.

### Green

After adding the repository, service, CLI, and script registration:

```powershell
Set-Location 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation'
uv run --directory MCP python -m pytest tests/test_work_service.py tests/test_novel_init.py -q
```

Output:

```text
......                                                                   [100%]
6 passed in 0.30s
```

## Verification Commands and Outputs

### Focused and Regression Checks

```powershell
Set-Location 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation'
uv run --directory MCP python -m pytest -q
```

Output:

```text
............                                                             [100%]
12 passed in 0.40s
```

### Quality Check

First Ruff run found one test line-length issue:

```powershell
Set-Location 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation'
uv run --directory MCP ruff check .
```

Output:

```text
E501 Line too long (89 > 88)
  --> tests\test_work_service.py:21:89
```

After wrapping that function signature:

```powershell
Set-Location 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation'
uv run --directory MCP ruff check .
```

Output:

```text
All checks passed!
```

### Packaging Validation

```powershell
Set-Location 'C:/Users/weito/Documents/src/NovelProduction-phase1-mcp-foundation'
python -m pip install --dry-run -e MCP
```

Key output:

```text
Would install ... novel-production-mcp-0.1.0 ...
```

`MCP/pyproject.toml` was inspected after the dry run. The only runtime console script added is:

```toml
[project.scripts]
novel-init = "novel_mcp.cli:main"
```

## Behavior Implemented

- `open_database(...)` still only opens and migrates the database.
- `initialize_work(db_path, title)` explicitly creates the single work row.
- initialization rejects blank titles
- initialization rejects duplicate runs with `WORK_EXISTS`
- `WorkService.update(title, expected_version)` trims and validates title text
- stale version updates raise `VERSION_CONFLICT`
- successful updates increment `version`

## Concerns

- The brief-specified raw `python -m pytest ...` command could not run directly because the host Python environment does not have `pytest` installed. All verification used the repo-managed `uv run --directory MCP ...` environment instead.
- `python -m pip install --dry-run -e MCP` generated temporary `egg-info` metadata under `MCP/src/`; those generated files were removed before staging source changes.
