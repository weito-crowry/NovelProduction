# Task 1 Report

## Scope

Implemented the Task 1 repository development foundation and SQLite database
lifecycle inside `MCP/`, with no Phase 2/3 behavior, no 003/004 migrations,
no ORM, no web layer, and no generated story data.

## Files Changed

- Created `.editorconfig`
- Created `.python-version`
- Created `.github/workflows/mcp-ci.yml`
- Created `MCP/.pre-commit-config.yaml`
- Created `MCP/scripts/check_source_size.py`
- Created `MCP/migrations/001_initial.sql`
- Modified `MCP/pyproject.toml`
- Created `MCP/src/novel_mcp/__init__.py`
- Created `MCP/src/novel_mcp/config.py`
- Created `MCP/src/novel_mcp/database.py`
- Created `MCP/src/novel_mcp/errors.py`
- Created `MCP/tests/test_database_lifecycle.py`
- Created `MCP/tests/test_development_foundation.py`
- Created `MCP/uv.lock`
- Removed `MCP/migrations/.gitkeep`

## Red-Green Evidence

### Red

1. Wrote focused tests first in `MCP/tests/test_database_lifecycle.py` and
   `MCP/tests/test_development_foundation.py`.
2. Initial targeted command from the brief:

   ```powershell
   uv run pytest MCP/tests/test_database_lifecycle.py::test_open_database_applies_connection_defaults_and_migrations -q
   ```

   Output:

   ```text
   error: Failed to spawn: `pytest`
     Caused by: program not found
   ```

3. Re-ran the same focused test with ephemeral pytest so the missing
   implementation failure could be observed before any production code:

   ```powershell
   cd MCP
   uv run --with pytest pytest tests/test_database_lifecycle.py::test_open_database_applies_connection_defaults_and_migrations -q
   ```

   Output:

   ```text
   ModuleNotFoundError: No module named 'novel_mcp.database'
   ```

4. After aligning the test signature to the brief, re-ran the same focused
   red test and observed the same expected missing-module failure:

   ```text
   ModuleNotFoundError: No module named 'novel_mcp.database'
   ```

### Green

After implementing the minimal lifecycle and foundation code:

```powershell
cd MCP
uv sync --all-groups
uv run pytest tests/test_database_lifecycle.py -q
```

Output after fixing the first implementation defects:

```text
....                                                                     [100%]
4 passed in 0.42s
```

## Commands And Outputs

### Repository inspection

```powershell
git -C C:\Users\weito\Documents\src\NovelProduction status --short --branch
```

Output:

```text
## main...origin/main
```

```powershell
git -C C:\Users\weito\Documents\src\NovelProduction rev-parse --git-dir
git -C C:\Users\weito\Documents\src\NovelProduction rev-parse --git-common-dir
git -C C:\Users\weito\Documents\src\NovelProduction branch --show-current
```

Output:

```text
.git
.git
main
```

### Dependency/bootstrap

```powershell
cd MCP
uv sync --all-groups
```

Output summary:

```text
Resolved 58 packages
Installed pytest, pytest-cov, ruff, mypy, pre-commit, and lockfile content
```

### Focused tests

```powershell
cd MCP
uv run pytest tests/test_database_lifecycle.py -q
uv run pytest tests/test_development_foundation.py -q
```

Output:

```text
....                                                                     [100%]
4 passed in 0.42s

.                                                                        [100%]
1 passed in 0.01s
```

### Quality checks

```powershell
cd MCP
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pre-commit run --all-files
```

Output:

```text
All checks passed!
8 files already formatted
Success: no issues found in 4 source files
ruff check...........................................(no files to check)Skipped
ruff format..........................................(no files to check)Skipped
fix end of files.........................................................Passed
trim trailing whitespace.................................................Passed
```

### Source-size and migration inventory

```powershell
python MCP/scripts/check_source_size.py
Get-ChildItem MCP/migrations
```

Output:

```text
source-size checks passed

Directory: C:\Users\weito\Documents\src\NovelProduction\MCP\migrations
-a--- 001_initial.sql
```

## Schema Decisions

- Kept `001_initial.sql` limited to the Task 1 / Phase 1 lifecycle boundary:
  `schema_migrations`, `works`, `world_facts`, `timeline_events`,
  `timeline_event_participants`, `timeline_event_relations`, `characters`,
  `relationships`, `canon_decisions`, and `canon_decision_changes`.
- Did not add Chapter/Episode/Scene, disclosure/knowledge, state-log, or
  draft tables to `001_initial.sql`; those remain deferred to later migrations
  per the task boundary.
- Added `version INTEGER NOT NULL DEFAULT 1` on mutable Phase 1 entities so
  Task 1 does not preclude later optimistic-lock enforcement.
- Applied connection defaults in `open_database()`:
  `foreign_keys = ON`, `journal_mode = WAL`, `busy_timeout = 5000`.
- Implemented lexically ordered migration application with per-file checksum
  recording in `schema_migrations`.
- Rejected reuse of an already-applied filename when the file bytes differ.
- Executed migration statements inside an explicit transaction using
  statement-by-statement execution instead of `executescript()`, because the
  first attempt did not provide the rollback behavior the focused test required.
- Logging is limited to migration filenames on failure; migration SQL content,
  prose-like bodies, and database payloads are not logged.

## Concerns

- The current checkout reports `git-dir == git-common-dir == .git` on branch
  `main`, so I could not independently verify linked-worktree provenance even
  though I stayed within the provided checkout.
- The first red run needed `uv run --with pytest` because the repo did not yet
  have the Task 1 development dependencies installed; the final repository
  state now supports the brief’s intended `uv sync --all-groups` workflow.

## Fix Round 1

### Scope

- Kept work inside
  `C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation`.
- Verified `git branch --show-current` is `codex/phase1-mcp-foundation`
  before repo work.
- Addressed only the two review findings:
  Phase 1 80% coverage enforcement and Ruff rule expansion to `E,F,I,UP,B`.
- Preserved the parked items:
  `requires-python = ">=3.10"`, `.python-version = 3.13`, CI Python 3.13,
  and source-size checks limited to `MCP/src` and `MCP/tests`.

### Red-Green Evidence

Focused test added first in `MCP/tests/test_development_foundation.py`:

```powershell
cd C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation\MCP
uv run pytest tests/test_development_foundation.py::test_development_foundation_enforces_phase1_coverage_and_ruff_rules -q
```

Red output:

```text
FAILED tests/test_development_foundation.py::test_development_foundation_enforces_phase1_coverage_and_ruff_rules
assert 'fail_under = 80' in pyproject_text
```

After updating `MCP/pyproject.toml` and `.github/workflows/mcp-ci.yml`:

```powershell
uv run pytest tests/test_development_foundation.py::test_development_foundation_enforces_phase1_coverage_and_ruff_rules -q
```

Green output:

```text
.                                                                        [100%]
1 passed in 0.03s
```

### Commands And Outputs

Branch verification:

```powershell
cd C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation
git branch --show-current
```

Output:

```text
codex/phase1-mcp-foundation
```

Coverage-enabled suite:

```powershell
cd C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation\MCP
uv run pytest --cov=src/novel_mcp --cov-report=term-missing
```

Output:

```text
6 passed
Required test coverage of 80.0% reached. Total coverage: 97.47%
```

Required validation commands remained usable:

```powershell
uv run pytest tests/test_database_lifecycle.py -q
uv run pytest tests/test_development_foundation.py -q
```

Output:

```text
4 passed in 0.32s
2 passed in 0.04s
```

Quality checks:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pre-commit run --all-files
python C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation\MCP\scripts\check_source_size.py
```

Output:

```text
All checks passed!
8 files already formatted
Success: no issues found in 4 source files
ruff check...............................................................Passed
ruff format..............................................................Passed
fix end of files.........................................................Passed
trim trailing whitespace.................................................Passed
source-size checks passed
```

### Config Decisions

- Coverage enforcement lives in `MCP/pyproject.toml` under
  `[tool.coverage.run]` and `[tool.coverage.report]` with
  `source = ["src/novel_mcp"]`, `fail_under = 80`, and `show_missing = true`.
- CI enforces the gate with
  `uv run pytest --cov=src/novel_mcp --cov-report=term-missing`.
- Bare targeted pytest commands remain unchanged and usable because the
  coverage gate is not injected into global pytest `addopts`.
- Ruff `select` now includes `E`, `F`, `I`, `UP`, and `B`.

## Fix Round 1 Continuation

### Scope

- Kept work inside
  `C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation`.
- Verified branch `codex/phase1-mcp-foundation` before repo work.
- Restored only the tracked root `data/.gitkeep` placeholder.
- Did not restore `MCP/src/novel_mcp/.gitkeep` or `MCP/tests/.gitkeep`.
- Did not touch the unrelated plan/spec edits.

### Focused Red-Green

Red check for a newline-terminated tracked placeholder:

```powershell
cd C:\Users\weito\Documents\src\NovelProduction-phase1-mcp-foundation
python -c "from pathlib import Path; import sys; p=Path('data/.gitkeep'); data=p.read_bytes() if p.exists() else None; print(repr(data)); sys.exit(0 if p.is_file() and data == b'\n' else 1)"
```

Red output:

```text
b''
```

After rewriting `data/.gitkeep` as a one-line placeholder file:

```powershell
python -c "from pathlib import Path; import sys; p=Path('data/.gitkeep'); data=p.read_bytes() if p.exists() else None; print(repr(data)); sys.exit(0 if p.is_file() and data == b'\n' else 1)"
```

Green output:

```text
b'\n'
```

### Focused Repository And Format Checks

```powershell
git branch --show-current
git diff --check -- data/.gitkeep
git status --short -- data/.gitkeep
```

Output:

```text
codex/phase1-mcp-foundation
warning: in the working copy of 'data/.gitkeep', LF will be replaced by CRLF the next time Git touches it
 M data/.gitkeep
```
