# Phase C Read-only SQLite Runtime Blocker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every API GET path open SQLite with `mode=ro`, verify the canonical migrations without applying them, preserve temporary FTS search behavior, and prevent the Phase C read-only runtime from checkpointing or mutating `story.db`/`story.db-wal`.

**Architecture:** CORE will expose a separate read-only connection path that uses a Windows-safe SQLite URI with `mode=ro` and performs only local PRAGMA settings plus read-only migration verification. API write contexts continue to use `open_database()` unchanged, while every project-scoped GET and `ProjectRegistry._summarize()` use a read-only service context. Tests will exercise real temporary SQLite files, including a writer-held WAL fixture, and a mechanical route-boundary check will prevent GET regressions.

**Tech Stack:** Python 3.10+, stdlib `sqlite3`, FastAPI, pytest, pytest-cov, Ruff, mypy, uv.

**Spec:** Issue #9, approved Phase C post-merge read-only SQLite runtime blocker request.

## Global Constraints

- Never open `data/2126/story.db` or any stable story database during implementation or verification.
- Never use `immutable=1` or `PRAGMA query_only=ON` for the production read-only connection.
- Read-only connections must use SQLite URI `mode=ro`, must not mkdir, enable WAL, apply migrations, or write `schema_migrations`.
- Existing write routes retain the current `open_project_services()` behavior and transaction/version semantics.
- Migrations 001–004 remain canonical; migration 005 remains absent.
- MCP contract remains unchanged: 59 tools, 55/55 required `project_id`, no `project_select`, HTTP-only runtime, no CORE/SQLite fallback.
- Preserve existing untracked `.worktrees/` and `MCP/.tools/`; do not clean, stash, reset, rebase, or force-push.
- Work sequentially in this branch; do not delegate or use parallel agents.

---

### Task 1: Add CORE read-only SQLite lifecycle and migration verification

**Files:**
- Modify: `CORE/src/novel_core/database.py`
- Test: `CORE/tests/test_readonly_database.py`

**Interfaces:**
- Produces `open_database_readonly(config: DatabaseConfig) -> sqlite3.Connection`.
- Produces `assert_migrations_current(connection: sqlite3.Connection, migration_dir: Path) -> None` or an equivalent private/public helper following existing naming style.
- Existing `open_database()` and `apply_migrations()` remain write-capable and behavior-compatible.

- [x] **Step 1: Write failing tests for read-only open.** Add tests proving a temporary initialized database can be read, that `INSERT`, `UPDATE`, and DDL fail through the returned connection, that a database missing a migration fails closed without adding rows to `schema_migrations`, and that the SQLite URI uses `mode=ro` without `immutable=1` or `PRAGMA query_only`.

- [x] **Step 2: Write the failing WAL-preservation test.** Create a temporary writer connection in WAL mode with autocheckpoint suppressed, commit a row while keeping the writer open, hash `story.db` and `story.db-wal`, open/read/close through `open_database_readonly()`, then assert both hashes, sizes, and WAL presence are unchanged before closing the writer.

- [x] **Step 3: Run the focused CORE tests and verify the expected failure.**

```powershell
Set-Location CORE
uv run pytest tests/test_database_lifecycle.py -q
```

Expected: the new tests fail because the read-only entry point and verification helper do not yet exist or because the current read-write open mutates the fixture.

- [x] **Step 4: Implement the minimal read-only connection.** Build the URI with `Path.resolve().as_uri()` plus `mode=ro`, call `sqlite3.connect(uri, uri=True)`, set only `foreign_keys=ON` and `busy_timeout=5000`, and invoke read-only migration verification. Do not call `mkdir`, `journal_mode=WAL`, `apply_migrations`, or `query_only`.

- [x] **Step 5: Implement read-only migration verification.** Check that `schema_migrations` exists, every migration file in the canonical directory is applied, no applied migration is missing from the inventory, and each stored checksum matches the existing canonical/raw/CRLF-compatible checksum candidates. Raise the existing `MigrationError` family without mutating the connection.

- [x] **Step 6: Run the focused CORE tests and verify they pass.**

```powershell
uv run pytest tests/test_database_lifecycle.py -q
```

- [x] **Step 7: Run CORE service/search regressions.**

```powershell
uv run pytest tests/test_japanese_search.py tests/test_world_fact_service.py tests/test_character_service.py -q
```

Confirm temporary FTS/trigram search remains usable and no caller-owned transaction behavior is changed.

### Task 2: Separate API read and write service contexts

**Files:**
- Modify: `API/src/novel_api/service_container.py`
- Modify: `API/src/novel_api/project_registry.py`
- Modify: `API/src/novel_api/routes/authoring.py`
- Modify: `API/src/novel_api/routes/canon.py`
- Modify: `API/src/novel_api/routes/characters.py`
- Modify: `API/src/novel_api/routes/information.py`
- Modify: `API/src/novel_api/routes/narrative.py`
- Modify: `API/src/novel_api/routes/timeline.py`
- Modify: `API/src/novel_api/routes/views.py`
- Modify: `API/src/novel_api/routes/work.py`
- Modify: `API/src/novel_api/routes/world.py`
- Test: `API/tests/test_request_connections.py`
- Test: `API/tests/test_phase1_api.py`
- Test: `API/tests/test_phase2_api.py`
- Test: `API/tests/test_phase3_api.py`
- Test: `API/tests/test_projects.py`

**Interfaces:**
- Produces `open_project_read_services(target: ProjectTarget) -> Iterator[ServiceContainer]` backed by CORE `open_database_readonly()`.
- Keeps `open_project_services(target)` backed by existing `open_database()` for POST/PATCH/PUT/DELETE routes.

- [x] **Step 1: Write failing API context and route-boundary tests.** Assert the new read context is used for representative GETs, the write context remains used by write handlers, `ProjectRegistry._summarize()` uses the read-only opener, and no GET route source contains `open_project_services`.

- [x] **Step 2: Run the focused API tests and verify the expected failure.**

```powershell
Set-Location API
uv run pytest tests/test_request_connections.py tests/test_projects.py tests/test_phase1_api.py tests/test_phase2_api.py tests/test_phase3_api.py -q
```

- [x] **Step 3: Add the read service context and migrate all project-scoped GET handlers.** Replace only GET context usage; leave each write handler on `open_project_services()` and preserve route response models, error handling, and service calls.

- [x] **Step 4: Change `ProjectRegistry._summarize()` to use read-only open.** Preserve `metadata_state=missing|invalid`, active fallback, health calculation, and the no-repair/no-generation behavior for `project.json`.

- [x] **Step 5: Run focused API tests and verify they pass.**

```powershell
uv run pytest tests/test_request_connections.py tests/test_projects.py tests/test_phase1_api.py tests/test_phase2_api.py tests/test_phase3_api.py -q
```

### Task 3: Add integration, search, and route inventory regressions

**Files:**
- Modify: `API/tests/test_views.py`
- Create: `API/tests/test_read_only_routes.py`
- Modify: `CORE/tests/test_japanese_search.py`

**Interfaces:**
- Tests use only temporary project roots and temporary story databases.
- The mechanical boundary test derives the route inventory from route source decorators and asserts every project-scoped GET is backed by the read context.

- [x] **Step 1: Add temporary API hash-preservation tests.** Exercise `/projects`, `/projects/{id}`, `/work`, `/world-facts/search`, `/chapters`, `/episodes/{id}/context`, and `/episodes/{id}/drafts`; compare `story.db` and existing WAL hashes before and after.

- [x] **Step 2: Add read-only search regressions.** Exercise `world_fact_search` and `character_search`, including the existing trigram-capable route where available, through a mode=ro connection and assert Japanese query results remain valid.

- [x] **Step 3: Run the new integration tests and verify they pass.**

```powershell
Set-Location API
uv run pytest tests/test_read_only_routes.py tests/test_multi_project_e2e.py tests/test_views.py -q
Set-Location ..\CORE
uv run pytest tests/test_japanese_search.py -q
```

### Task 4: Update the cutover runbook without touching production

**Files:**
- Modify: `docs/runbooks/phase-c-mcp-http-cutover.md`

- [x] **Step 1: Document the corrected baseline order.** State: stop old direct MCP/runtime; confirm no process holds the DB; wait for SQLite quiescence; record `story.db`/WAL baseline; start the new API; run read-only dogfood; compare hash/size/presence; treat SHM separately.

- [x] **Step 2: State that stable DB, Tunnel, Connector, controlled writes, and Phase D remain out of scope for this fix.** Keep the existing rollback guidance and HTTP-only MCP requirement.

- [x] **Step 3: Run documentation and diff checks.**

```powershell
git diff --check
```

### Task 5: Full verification, commit, push, and Draft PR

**Files:**
- Modify only the files from Tasks 1–4 and the plan document.

- [x] **Step 1: Run CORE gates.**

```powershell
Set-Location CORE
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error --cov=novel_core --cov-report=term-missing
```

- [x] **Step 2: Run API gates.**

```powershell
Set-Location ..\API
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error --cov=novel_api --cov-report=term-missing
```

- [x] **Step 3: Run MCP and repository gates without stable runtime.** Verify 59 tools, 55 required `project_id` fields, no `project_select`, no CORE/SQLite imports, repository boundaries, source size, migration 001–004 identity, migration 005 absence, and pre-commit.

- [x] **Step 4: Review the final diff and status.** Confirm no stable DB access, no Tunnel/Connector change, no controlled write, no unrelated tracked files, and only the intended branch changes.

- [ ] **Step 5: Commit the focused fix.**

```powershell
git add CORE API docs/superpowers/plans/2026-08-28-novelproduction-phase-c-readonly-sqlite.md
git commit -m "fix: make API read paths SQLite read-only"
```

- [ ] **Step 6: Push the branch without force.**

```powershell
git push -u origin codex/phase-c-readonly-sqlite
```

- [ ] **Step 7: Create a Draft PR against `main`.** Use title `fix: make API read paths SQLite read-only`; include `Refs #9`, the WAL-preservation evidence, route-boundary coverage, full verification results, and explicit statements that stable DB, Tunnel, Connector, controlled writes, and Phase D were untouched. Do not merge or close Issue #9.
