# NovelProduction Phase A CORE Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the existing Phase 1–3 domain/database implementation from `novel_mcp` into a reusable `novel_core` package without changing MCP tool behavior, tool inventory, story semantics, or the real production database.

**Architecture:** Phase A is a behavior-preserving extraction only. `CORE/` becomes the owner of database lifecycle, migrations, errors, models, repositories, services, context projection/guards, and explicit work initialization; `MCP/` remains a direct in-process consumer of CORE until Phase C replaces that dependency with HTTP. Thin MCP compatibility facades may remain for `config`, `database`, `errors`, and the `novel-init` CLI, but all implementation logic must live in `novel_core` by the end of this phase.

**Tech Stack:** Python 3.10+ runtime, Python 3.13 CI/type-check target, stdlib `sqlite3`, setuptools, uv, pytest, pytest-cov, Ruff, mypy, pre-commit, MCP Python SDK.

**Spec:** `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

## Global Constraints

- Do not modify or initialize the real `data/2126/story.db` during Phase A.
- Do not change MCP tool names, input/output semantics, or the total Phase 1–3 tool inventory of 55 tools.
- Do not add HTTP/API behavior in Phase A; MCP remains CORE-direct until Phase C.
- Migrations `001_initial.sql`, `002_search.sql`, `003_narrative.sql`, and `004_drafts.sql` move to `CORE/migrations/` with byte/content identity preserved; no SQL edits.
- Preserve the EOL-independent migration checksum behavior already implemented in `database.py`.
- No new schema migration is introduced in Phase A; migration `005` belongs to Phase E.
- Preserve SQLite safety settings: `PRAGMA foreign_keys=ON`, WAL, and `busy_timeout=5000`.
- Preserve explicit transaction ownership and the search -> write regression fix; search must not leave an implicit transaction that breaks a later `BEGIN IMMEDIATE`.
- Preserve optimistic version checks, canon behavior, future/disclosure-safe episode context, append-only drafts, and all Phase 1–3 guards.
- `CORE` must not import `novel_mcp`, `mcp`, FastAPI, React, TipTap, or future API/WEBUI packages.
- MCP-specific tool registration, tool descriptions, tool annotations, structured MCP output, and MCP error adaptation remain under `MCP/src/novel_mcp/`.
- Do not delete the old real DB or cut over Tunnel/ChatGPT Connector in this phase.

---

## File Structure After Phase A

The implementation should end with the following ownership boundary:

```text
CORE/
├─ migrations/
│  ├─ 001_initial.sql
│  ├─ 002_search.sql
│  ├─ 003_narrative.sql
│  └─ 004_drafts.sql
├─ pyproject.toml
├─ src/novel_core/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ database.py
│  ├─ errors.py
│  ├─ initialization.py
│  ├─ models/
│  │  ├─ __init__.py
│  │  ├─ context.py
│  │  └─ outline.py
│  ├─ repositories/
│  │  ├─ __init__.py
│  │  ├─ canon_repository.py
│  │  ├─ character_repository.py
│  │  ├─ character_state_repository.py
│  │  ├─ context_repository.py
│  │  ├─ disclosure_repository.py
│  │  ├─ draft_repository.py
│  │  ├─ episode_reference_repository.py
│  │  ├─ information_repository.py
│  │  ├─ knowledge_repository.py
│  │  ├─ narrative_repository.py
│  │  ├─ outline_repository.py
│  │  ├─ relationship_repository.py
│  │  ├─ search_repository.py
│  │  ├─ timeline_repository.py
│  │  ├─ work_repository.py
│  │  └─ world_fact_repository.py
│  └─ services/
│     ├─ __init__.py
│     ├─ canon_service.py
│     ├─ character_service.py
│     ├─ character_state_service.py
│     ├─ context_guards.py
│     ├─ context_projection.py
│     ├─ context_service.py
│     ├─ disclosure_service.py
│     ├─ draft_service.py
│     ├─ episode_reference_service.py
│     ├─ information_service.py
│     ├─ knowledge_service.py
│     ├─ narrative_service.py
│     ├─ outline_service.py
│     ├─ relationship_service.py
│     ├─ search_service.py
│     ├─ timeline_service.py
│     ├─ work_service.py
│     └─ world_fact_service.py
└─ tests/
   └─ domain/database tests moved from MCP

MCP/
├─ pyproject.toml
├─ src/novel_mcp/
│  ├─ cli.py                 # CLI adapter only
│  ├─ config.py              # temporary compatibility re-export only
│  ├─ database.py            # temporary compatibility re-export only
│  ├─ errors.py              # temporary compatibility re-export only
│  ├─ mcp_server.py
│  ├─ phase1_tools.py
│  ├─ phase2_tools.py
│  ├─ phase3_tools.py
│  ├─ phase3_acceptance*.py
│  ├─ tool_descriptions.py
│  ├─ phase2_tool_descriptions.py
│  ├─ phase3_tool_descriptions.py
│  ├─ tool_errors.py
│  └─ tool_support.py
└─ tests/
   └─ MCP/CLI/acceptance tests only
```

`MCP/src/novel_mcp/repositories/`, `services/`, and `models/` must not remain as duplicate implementations after the extraction.

---

### Task 1: Create the standalone CORE package and move database lifecycle ownership

**Files:**
- Create: `CORE/pyproject.toml`
- Create: `CORE/src/novel_core/__init__.py`
- Create: `CORE/src/novel_core/config.py`
- Create: `CORE/src/novel_core/database.py`
- Create: `CORE/src/novel_core/errors.py`
- Move unchanged: `MCP/migrations/001_initial.sql` -> `CORE/migrations/001_initial.sql`
- Move unchanged: `MCP/migrations/002_search.sql` -> `CORE/migrations/002_search.sql`
- Move unchanged: `MCP/migrations/003_narrative.sql` -> `CORE/migrations/003_narrative.sql`
- Move unchanged: `MCP/migrations/004_drafts.sql` -> `CORE/migrations/004_drafts.sql`
- Move/adapt: `MCP/tests/test_database_lifecycle.py` -> `CORE/tests/test_database_lifecycle.py`
- Modify: `.gitattributes`

**Interfaces:**
- Produces: `novel_core.config.DatabaseConfig(db_path: Path, migration_dir: Path)`
- Produces: `novel_core.database.open_database(config: DatabaseConfig) -> sqlite3.Connection`
- Produces: `novel_core.database.default_migration_dir() -> Path`
- Produces: the current domain exception classes under `novel_core.errors`
- Consumes: no MCP package code.

- [ ] **Step 1: Write the CORE package metadata and a failing import/lifecycle test**

Create `CORE/pyproject.toml` with no runtime dependencies and the same quality gates used by the current Python codebase:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "novel-production-core"
version = "0.1.0"
description = "NovelProduction shared domain and SQLite core"
requires-python = ">=3.10"
dependencies = []

[dependency-groups]
dev = [
    "mypy>=1.18.0",
    "pre-commit>=4.3.0",
    "pytest>=8.4.0",
    "pytest-cov>=7.0.0",
    "ruff>=0.12.0",
]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.mypy]
python_version = "3.13"
strict = true

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src/novel_core"]

[tool.coverage.report]
fail_under = 80
show_missing = true

[tool.ruff]
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

At the top of the moved `CORE/tests/test_database_lifecycle.py`, change imports to:

```python
from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.errors import MigrationError
```

and use:

```python
MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"
```

- [ ] **Step 2: Run the moved lifecycle test and verify it fails before CORE code exists**

Run from `CORE/`:

```bash
uv sync --all-groups
uv run pytest tests/test_database_lifecycle.py -q
```

Expected: collection/import failure for `novel_core.config`, `novel_core.database`, or `novel_core.errors`.

- [ ] **Step 3: Copy database/config/error implementation into CORE without semantic edits**

Move the implementation bodies from:

```text
MCP/src/novel_mcp/config.py
MCP/src/novel_mcp/database.py
MCP/src/novel_mcp/errors.py
```

into the corresponding `novel_core` modules, replacing internal import prefixes `novel_mcp.` with `novel_core.` only.

Add this helper to `CORE/src/novel_core/database.py`:

```python
from pathlib import Path


def default_migration_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations"
```

Do not alter the existing checksum normalization algorithm: new stored migration checksums remain canonical-LF and existing raw/LF/CRLF candidates remain accepted.

- [ ] **Step 4: Move migration files and enforce LF at the new path**

Change `.gitattributes` to:

```gitattributes
CORE/migrations/*.sql text eol=lf
```

Move all four SQL files with `git mv`. Do not open/re-save them in an editor.

Verify their Git blob identities against the pre-extraction base commit:

```bash
base="$(git merge-base HEAD origin/main)"
test "$(git rev-parse HEAD:CORE/migrations/001_initial.sql)" = "$(git rev-parse "$base":MCP/migrations/001_initial.sql)"
test "$(git rev-parse HEAD:CORE/migrations/002_search.sql)" = "$(git rev-parse "$base":MCP/migrations/002_search.sql)"
test "$(git rev-parse HEAD:CORE/migrations/003_narrative.sql)" = "$(git rev-parse "$base":MCP/migrations/003_narrative.sql)"
test "$(git rev-parse HEAD:CORE/migrations/004_drafts.sql)" = "$(git rev-parse "$base":MCP/migrations/004_drafts.sql)"
```

Expected: all four `test` commands exit 0.

- [ ] **Step 5: Run CORE database lifecycle tests**

```bash
cd CORE
uv run pytest tests/test_database_lifecycle.py -q
```

Expected: PASS, including LF/CRLF reopen compatibility, mixed legacy checksum compatibility, and substantive migration-change fail-closed behavior.

- [ ] **Step 6: Run CORE static checks for the new package**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit**

```bash
git add CORE .gitattributes MCP/migrations MCP/tests/test_database_lifecycle.py
git commit -m "refactor: establish novel core database package"
```

---

### Task 2: Move domain models and repositories into CORE

**Files:**
- Move: `MCP/src/novel_mcp/models/*` -> `CORE/src/novel_core/models/*`
- Move: `MCP/src/novel_mcp/repositories/*` -> `CORE/src/novel_core/repositories/*`
- Move/adapt: `MCP/tests/test_japanese_search.py` -> `CORE/tests/test_japanese_search.py`
- Move/adapt: `MCP/tests/test_narrative_migration.py` -> `CORE/tests/test_narrative_migration.py`
- Move/adapt: `MCP/tests/test_narrative_reorder.py` -> `CORE/tests/test_narrative_reorder.py`

**Interfaces:**
- Consumes: `novel_core.config.DatabaseConfig`, `novel_core.database.open_database`, `novel_core.errors.*`
- Produces: all current record dataclasses and repository classes under `novel_core.models` / `novel_core.repositories` with unchanged public method signatures.

- [ ] **Step 1: Move the model/repository trees and rewrite only package-qualified imports**

Use `git mv` for each source file. In moved Python files, convert imports such as:

```python
from novel_mcp.errors import VersionConflictError
from novel_mcp.models.context import ContextBundle
```

to:

```python
from novel_core.errors import VersionConflictError
from novel_core.models.context import ContextBundle
```

Do not rename repository classes, record fields, SQL, ordering behavior, or transaction methods.

- [ ] **Step 2: Move repository-focused regression tests and update imports**

Move the three listed tests to `CORE/tests/`. Replace `novel_mcp.*` domain imports with `novel_core.*`. Where a test currently imports `initialize_work` from `novel_mcp.cli`, temporarily replace setup with direct `WorkRepository.create(...)` inside an explicit transaction until Task 4 introduces `novel_core.initialization.initialize_work`.

Use this exact setup shape when needed:

```python
repository = WorkRepository(connection)
repository.begin_write()
repository.create(slug="main", working_title="2126")
repository.commit()
```

- [ ] **Step 3: Run the moved repository/search regressions**

```bash
cd CORE
uv run pytest \
  tests/test_japanese_search.py \
  tests/test_narrative_migration.py \
  tests/test_narrative_reorder.py -q
```

Expected: PASS, including trigram/substring search behavior and reorder transaction behavior.

- [ ] **Step 4: Assert CORE has no MCP dependency**

From repository root:

```bash
if rg -n "(^|\s)(from|import) novel_mcp|from mcp|import mcp" CORE/src/novel_core; then
  echo "CORE must not import MCP" >&2
  exit 1
fi
```

Expected: no matches.

- [ ] **Step 5: Run CORE static checks**

```bash
cd CORE
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add CORE MCP/src/novel_mcp/models MCP/src/novel_mcp/repositories MCP/tests
 git commit -m "refactor: move domain models and repositories to core"
```

---

### Task 3: Move domain services and authoring/context logic into CORE

**Files:**
- Move: every file under `MCP/src/novel_mcp/services/` -> `CORE/src/novel_core/services/`
- Move/adapt domain tests:
  - `MCP/tests/test_canon_service.py` -> `CORE/tests/test_canon_service.py`
  - `MCP/tests/test_character_service.py` -> `CORE/tests/test_character_service.py`
  - `MCP/tests/test_character_state_service.py` -> `CORE/tests/test_character_state_service.py`
  - `MCP/tests/test_context_leakage.py` -> `CORE/tests/test_context_leakage.py`
  - `MCP/tests/test_context_service.py` -> `CORE/tests/test_context_service.py`
  - `MCP/tests/test_disclosure_service.py` -> `CORE/tests/test_disclosure_service.py`
  - `MCP/tests/test_draft_service.py` -> `CORE/tests/test_draft_service.py`
  - `MCP/tests/test_episode_reference_service.py` -> `CORE/tests/test_episode_reference_service.py`
  - `MCP/tests/test_information_service.py` -> `CORE/tests/test_information_service.py`
  - `MCP/tests/test_knowledge_service.py` -> `CORE/tests/test_knowledge_service.py`
  - `MCP/tests/test_narrative_service.py` -> `CORE/tests/test_narrative_service.py`
  - `MCP/tests/test_outline_service.py` -> `CORE/tests/test_outline_service.py`
  - `MCP/tests/test_relationship_service.py` -> `CORE/tests/test_relationship_service.py`
  - `MCP/tests/test_timeline_service.py` -> `CORE/tests/test_timeline_service.py`
  - `MCP/tests/test_work_service.py` -> `CORE/tests/test_work_service.py`
  - `MCP/tests/test_world_fact_service.py` -> `CORE/tests/test_world_fact_service.py`

**Interfaces:**
- Consumes: CORE repositories/models/errors.
- Produces: the existing `CanonService`, `CharacterService`, `CharacterStateService`, `ContextService`, `DisclosureService`, `DraftService`, `EpisodeReferenceService`, `InformationService`, `KnowledgeService`, `NarrativeService`, `OutlineService`, `RelationshipService`, `SearchService`, `TimelineService`, `WorkService`, and `WorldFactService` with unchanged call signatures.

- [ ] **Step 1: Move all service modules and rewrite package imports**

For each moved file, replace only module ownership prefixes. Example:

```python
from novel_mcp.repositories.narrative_repository import NarrativeRepository
```

becomes:

```python
from novel_core.repositories.narrative_repository import NarrativeRepository
```

Keep `context_guards.py` and `context_projection.py` in CORE because they implement authoring-domain behavior, not MCP transport behavior.

- [ ] **Step 2: Move service/domain tests and change imports to `novel_core`**

Move the listed tests. For every `open_test_database`, point `migration_dir` to:

```python
Path(__file__).resolve().parents[1] / "migrations"
```

Do not relax assertions or remove negative/future-safety cases to make the extraction pass.

- [ ] **Step 3: Run the complete CORE test suite**

```bash
cd CORE
uv run pytest -W error
```

Expected: every moved database/repository/service/context/draft test passes.

- [ ] **Step 4: Run coverage and static checks**

```bash
uv run pytest -W error --cov=src/novel_core --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: coverage >= 80%; all static checks PASS.

- [ ] **Step 5: Verify CORE import direction**

```bash
cd ..
if rg -n "(^|\s)(from|import) novel_mcp|from mcp|import mcp" CORE/src/novel_core; then
  echo "CORE imports an adapter package" >&2
  exit 1
fi
```

Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add CORE MCP/src/novel_mcp/services MCP/tests
git commit -m "refactor: move novel domain services to core"
```

---

### Task 4: Move explicit work initialization into CORE and preserve the `novel-init` CLI adapter

**Files:**
- Create: `CORE/src/novel_core/initialization.py`
- Modify: `CORE/tests/test_work_service.py`
- Modify: `MCP/src/novel_mcp/cli.py`
- Keep/test: `MCP/tests/test_novel_init.py`
- Modify: `MCP/src/novel_mcp/config.py`
- Modify: `MCP/src/novel_mcp/database.py`
- Modify: `MCP/src/novel_mcp/errors.py`

**Interfaces:**
- Produces: `novel_core.initialization.initialize_work(...) -> WorkRecord`
- Produces: `novel_core.initialization.DEFAULT_WORK_SLUG = "main"`
- Preserves: `novel_mcp.cli.initialize_work` as an imported/re-exported compatibility name during Phase A.
- Preserves: `novel-init` command behavior and arguments.

- [ ] **Step 1: Add a failing CORE initialization test**

Update `CORE/tests/test_work_service.py` to import:

```python
from novel_core.initialization import initialize_work
```

and keep the existing cases that prove explicit initialization, duplicate rejection, versioning, JSON validation, and no implicit work creation.

Run:

```bash
cd CORE
uv run pytest tests/test_work_service.py -q
```

Expected: FAIL because `novel_core.initialization` does not exist yet.

- [ ] **Step 2: Implement CORE initialization by moving existing CLI domain logic**

Create `CORE/src/novel_core/initialization.py` with this public signature:

```python
from pathlib import Path

from novel_core.repositories.work_repository import WorkRecord

DEFAULT_WORK_SLUG = "main"


def initialize_work(
    db_path: Path,
    title: str | None = None,
    *,
    working_title: str | None = None,
    genre: str = "",
    premise: str = "",
    themes_json: str = "{}",
    description: str = "",
    production_status: str = "planned",
    migration_dir: Path | None = None,
) -> WorkRecord:
    ...
```

The body must preserve the current `novel_mcp.cli.initialize_work` validation and explicit transaction semantics. When `migration_dir is None`, use `novel_core.database.default_migration_dir()`.

- [ ] **Step 3: Reduce MCP CLI to argument parsing + CORE delegation**

`MCP/src/novel_mcp/cli.py` should import:

```python
from novel_core.initialization import initialize_work
from novel_core.services.work_service import PRODUCTION_STATUSES
```

Keep `build_parser()` and `main()` in MCP. Remove database/repository initialization logic from the MCP module.

- [ ] **Step 4: Convert MCP config/database/errors modules to zero-logic compatibility facades**

Use explicit re-exports only:

```python
# MCP/src/novel_mcp/config.py
from novel_core.config import DatabaseConfig

__all__ = ["DatabaseConfig"]
```

```python
# MCP/src/novel_mcp/database.py
from novel_core.database import default_migration_dir, open_database

__all__ = ["default_migration_dir", "open_database"]
```

For `MCP/src/novel_mcp/errors.py`, explicitly import/re-export the current exception names from `novel_core.errors`; do not duplicate class definitions.

- [ ] **Step 5: Run CORE and CLI tests**

```bash
cd CORE
uv run pytest tests/test_work_service.py -q
cd ../MCP
uv run pytest tests/test_novel_init.py -q
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add CORE/src/novel_core/initialization.py CORE/tests/test_work_service.py MCP/src/novel_mcp/cli.py MCP/src/novel_mcp/config.py MCP/src/novel_mcp/database.py MCP/src/novel_mcp/errors.py MCP/tests/test_novel_init.py
git commit -m "refactor: move work initialization into core"
```

---

### Task 5: Rewire MCP runtime and tools to consume CORE directly

**Files:**
- Modify: `MCP/pyproject.toml`
- Modify/regenerate: `MCP/uv.lock`
- Modify: `MCP/src/novel_mcp/mcp_server.py`
- Modify: `MCP/src/novel_mcp/phase1_tools.py`
- Modify: `MCP/src/novel_mcp/phase2_tools.py`
- Modify: `MCP/src/novel_mcp/phase3_tools.py`
- Modify: `MCP/src/novel_mcp/phase3_acceptance.py`
- Modify: `MCP/src/novel_mcp/phase3_acceptance_probes.py`
- Modify: `MCP/src/novel_mcp/phase3_acceptance_seed.py`
- Modify: `MCP/src/novel_mcp/tool_errors.py`
- Modify as needed: `MCP/src/novel_mcp/tool_support.py`
- Keep unchanged unless import-only edits are required: all `*_tool_descriptions.py`

**Interfaces:**
- Consumes: `novel-production-core` as an editable local path dependency.
- Preserves: `create_server(config: DatabaseConfig)`, `ALL_TOOL_NAMES`, MCP tool names, tool annotations, and structured output.
- Produces no HTTP client in Phase A.

- [ ] **Step 1: Add CORE as an explicit MCP package dependency**

Modify `MCP/pyproject.toml`:

```toml
[project]
dependencies = [
    "mcp>=2.0,<3.0",
    "novel-production-core",
]

[tool.uv.sources]
novel-production-core = { path = "../CORE", editable = true }
```

Run:

```bash
cd MCP
uv sync --all-groups
```

Expected: uv resolves `novel-production-core` from `../CORE` and regenerates `MCP/uv.lock` without fetching a registry package of that name.

- [ ] **Step 2: Rewire `mcp_server.py` to import CORE composition dependencies**

Keep `ServiceContainer` in MCP because it composes MCP handlers, but import its service types from `novel_core.services.*` and import `DatabaseConfig` / `open_database` from `novel_core`.

The composition shape remains:

```python
services = ServiceContainer(
    work=WorkService(connection),
    world=WorldFactService(connection),
    timeline=TimelineService(connection),
    character=CharacterService(connection),
    relationship=RelationshipService(connection),
    canon=CanonService(connection),
    search=SearchService(connection),
    narrative=NarrativeService(connection),
    state=CharacterStateService(connection),
    information=InformationService(connection),
    disclosure=DisclosureService(connection),
    knowledge=KnowledgeService(connection),
    references=EpisodeReferenceService(connection),
    drafts=DraftService(connection),
    outline=OutlineService(connection),
    context=ContextService(connection),
)
```

Do not change the registration order or `ToolAnnotations` values.

- [ ] **Step 3: Rewire tool modules and acceptance helpers**

Replace imports of domain types/errors/services/repositories/models from `novel_mcp` with `novel_core`. Keep MCP-only imports (`tool_support`, tool descriptions, registration helpers) under `novel_mcp`.

After edits, run from repository root:

```bash
rg -n "novel_mcp\.(services|repositories|models)" MCP/src MCP/tests
```

Expected: no matches.

- [ ] **Step 4: Run MCP tool and stdio regression tests**

```bash
cd MCP
uv run pytest -W error \
  tests/test_phase1_mcp_tools.py \
  tests/test_phase2_mcp_tools.py \
  tests/test_phase3_mcp_tools.py \
  tests/test_phase3_review_regressions.py \
  tests/test_phase3_stdio_smoke.py
```

Expected: PASS. In particular, the long-lived MCP search -> write regression must not reproduce `cannot start a transaction within a transaction`.

- [ ] **Step 5: Verify tool inventory remains exactly 55**

```bash
uv run python -c "from novel_mcp.mcp_server import ALL_TOOL_NAMES; assert len(ALL_TOOL_NAMES) == 55, len(ALL_TOOL_NAMES)"
```

Expected: exit 0.

- [ ] **Step 6: Run MCP static checks**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add MCP
 git commit -m "refactor: rewire mcp runtime to novel core"
```

---

### Task 6: Split CORE tests from MCP acceptance tests cleanly and remove duplicate domain implementation

**Files:**
- Remove after all imports are migrated: `MCP/src/novel_mcp/models/`
- Remove after all imports are migrated: `MCP/src/novel_mcp/repositories/`
- Remove after all imports are migrated: `MCP/src/novel_mcp/services/`
- Keep in MCP tests:
  - `MCP/tests/test_development_foundation.py`
  - `MCP/tests/test_novel_init.py`
  - `MCP/tests/test_phase1_acceptance.py`
  - `MCP/tests/test_phase1_mcp_tools.py`
  - `MCP/tests/test_phase2_canon.py`
  - `MCP/tests/test_phase2_mcp_tools.py`
  - `MCP/tests/test_phase3_acceptance.py`
  - `MCP/tests/test_phase3_acceptance_negative.py`
  - `MCP/tests/test_phase3_mcp_tools.py`
  - `MCP/tests/test_phase3_review_regressions.py`
  - `MCP/tests/test_phase3_stdio_smoke.py`

**Interfaces:**
- CORE tests own direct domain/database verification.
- MCP tests own adapter/tool/stdio/acceptance verification.
- No production domain class is implemented under `novel_mcp.services`, `novel_mcp.repositories`, or `novel_mcp.models` after this task.

- [ ] **Step 1: Run an ownership scan before deletion**

```bash
rg -n "novel_mcp\.(services|repositories|models)" MCP CORE
```

Expected: no import references remain. If a match is in historical documentation text only, do not change docs solely to satisfy the scan; scope the command to `*/src` and `*/tests` for the gate.

- [ ] **Step 2: Delete the old domain implementation directories**

```bash
git rm -r MCP/src/novel_mcp/models MCP/src/novel_mcp/repositories MCP/src/novel_mcp/services
```

Do not delete the thin `config.py`, `database.py`, or `errors.py` compatibility facades in Phase A.

- [ ] **Step 3: Run both complete test suites**

```bash
cd CORE
uv run pytest -W error
cd ../MCP
uv run pytest -W error
```

Expected: both PASS with no import from deleted domain directories.

- [ ] **Step 4: Run both coverage gates**

```bash
cd CORE
uv run pytest -W error --cov=src/novel_core --cov-report=term-missing
cd ../MCP
uv run pytest -W error --cov=src/novel_mcp --cov-report=term-missing
```

Expected: each configured coverage gate passes. Do not lower `fail_under=80` to make the extraction pass.

- [ ] **Step 5: Commit**

```bash
git add CORE MCP
 git commit -m "refactor: complete core ownership split"
```

---

### Task 7: Make repository tooling and CI understand CORE + MCP

**Files:**
- Modify: `.github/workflows/mcp-ci.yml`
- Modify: `MCP/scripts/check_source_size.py`
- Modify: `README.md`
- Modify: `MCP/README.md`
- Verify: `.gitattributes`

**Interfaces:**
- Produces: CI gates for both Python components.
- Preserves: current migration immutability and 55-tool inventory checks.

- [ ] **Step 1: Extend source-size checking to both components**

Change `MCP/scripts/check_source_size.py` so `main()` collects `src/**/*.py` and `tests/**/*.py` from both `CORE` and `MCP`:

```python
component_roots = (repo_root / "CORE", repo_root / "MCP")
src_files = sorted(
    path
    for root in component_roots
    for path in root.glob("src/**/*.py")
)
test_files = sorted(
    path
    for root in component_roots
    for path in root.glob("tests/**/*.py")
)
```

Keep existing size/line limits unchanged.

- [ ] **Step 2: Split CI into CORE and MCP jobs plus repository invariants**

Update `.github/workflows/mcp-ci.yml` to run, at minimum:

```yaml
jobs:
  core:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: CORE
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v6
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: uv sync --all-groups
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -W error
      - run: uv run pytest -W error --cov=src/novel_core --cov-report=term-missing

  mcp:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: MCP
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v6
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: uv sync --all-groups
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -W error
      - run: uv run pytest -W error --cov=src/novel_mcp --cov-report=term-missing
      - run: >-
          uv run python -c
          "from novel_mcp.mcp_server import ALL_TOOL_NAMES;
          assert len(ALL_TOOL_NAMES) == 55, len(ALL_TOOL_NAMES)"
```

Keep a repository-root invariant step that runs `git diff --check`, source-size checks, and migration blob/path checks.

- [ ] **Step 3: Update migration invariants for CORE ownership**

The repository invariant must assert the exact migration inventory:

```bash
actual_migrations="$(find CORE/migrations -maxdepth 1 -type f -name '*.sql' -printf '%f\n' | sort)"
expected_migrations="$(printf '%s\n' \
  001_initial.sql \
  002_search.sql \
  003_narrative.sql \
  004_drafts.sql)"
test "${actual_migrations}" = "${expected_migrations}"
test ! -d MCP/migrations
test ! -f data/story.db
```

For the extraction PR, compare each CORE migration blob against the base branch's corresponding MCP migration blob; fail if any differs.

- [ ] **Step 4: Update README ownership statements**

Root `README.md` should describe the implemented Phase A state, not claim only Phase 1 exists. Document:

```text
CORE/  shared domain/database package
MCP/   MCP adapter/runtime; temporarily CORE-direct until API cutover
API/   planned for Phase B
WEBUI/ planned for Phase D
data/  repository-wide story databases; not committed
```

`MCP/README.md` must state that domain/database implementation is owned by `CORE/` and that MCP direct CORE access is transitional until Phase C.

- [ ] **Step 5: Run repository-wide quality gates locally**

From repository root:

```bash
python MCP/scripts/check_source_size.py
git diff --check
cd CORE && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -W error
cd ../MCP && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -W error
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/mcp-ci.yml MCP/scripts/check_source_size.py README.md MCP/README.md .gitattributes CORE MCP
 git commit -m "ci: validate core and mcp components"
```

---

### Task 8: Phase A semantic-equivalence and cutover-readiness verification

**Files:**
- Test only; modify production files only if a failing regression proves the extraction changed behavior.
- Update: `docs/superpowers/plans/2026-08-28-novelproduction-phase-a-core-extraction.md` only to check completed boxes during execution if the worker tracks progress in-file.

**Interfaces:**
- Confirms the Phase A exit contract consumed by Phase B.

- [ ] **Step 1: Verify migration SQL identity one final time**

From repository root, with `base` set to the extraction branch base commit:

```bash
for name in 001_initial.sql 002_search.sql 003_narrative.sql 004_drafts.sql; do
  test "$(git rev-parse HEAD:CORE/migrations/$name)" = "$(git rev-parse "$base":MCP/migrations/$name)"
done
```

Expected: exit 0.

- [ ] **Step 2: Verify no adapter dependency leaked into CORE**

```bash
if rg -n "(^|\s)(from|import) (novel_mcp|mcp|fastapi)|from tiptap|import tiptap" CORE/src/novel_core; then
  echo "CORE dependency-direction violation" >&2
  exit 1
fi
```

Expected: no matches.

- [ ] **Step 3: Verify MCP has no duplicate domain implementation**

```bash
test ! -d MCP/src/novel_mcp/services
test ! -d MCP/src/novel_mcp/repositories
test ! -d MCP/src/novel_mcp/models
```

Expected: exit 0.

- [ ] **Step 4: Run the complete Python verification matrix**

```bash
cd CORE
uv sync --all-groups
uv run pytest -W error
uv run pytest -W error --cov=src/novel_core --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src

cd ../MCP
uv sync --all-groups
uv run pytest -W error
uv run pytest -W error --cov=src/novel_mcp --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -c "from novel_mcp.mcp_server import ALL_TOOL_NAMES; assert len(ALL_TOOL_NAMES) == 55"

cd ..
python MCP/scripts/check_source_size.py
git diff --check
```

Expected: all commands PASS.

- [ ] **Step 5: Run an isolated temporary-DB stdio smoke, including search -> write**

Use only a temporary database created under the test temp directory. Exercise in the same MCP process:

```text
work_get
world_fact_search(query with >=3 characters to force trigram FTS)
work_update(expected_version=<current>)
work_get
```

Expected:

```text
search succeeds (0 results is acceptable)
write succeeds
readback persists the intended field/version increment
no "cannot start a transaction within a transaction"
no INTERNAL_ERROR/database operation failed
```

Do not point this smoke at `data/2126/story.db`.

- [ ] **Step 6: Confirm the real DB and Tunnel configuration were untouched**

Before/after implementation, record filesystem metadata or a hash of the real DB if available without opening it for writes. Confirm no implementation command initialized, migrated, rewrote, or deleted the real DB. Confirm Tunnel/Connector configuration was not changed in Phase A.

- [ ] **Step 7: Commit any verification-only documentation change**

If no files changed, do not create an empty commit. If completion checkboxes or README verification notes changed:

```bash
git add docs README.md MCP/README.md
git commit -m "docs: record Phase A verification"
```

---

## Phase A Exit Criteria

Phase A is complete only when all of the following are true:

1. `CORE/` is an installable Python package named `novel-production-core`.
2. Migrations 001–004 live under `CORE/migrations/` and are byte/content-identical to the pre-extraction files.
3. Database lifecycle, models, repositories, services, context logic, and draft logic are implemented only under `novel_core`.
4. `CORE/src/novel_core` contains no dependency on MCP/API/WEBUI libraries or packages.
5. MCP remains operational as a direct CORE consumer; no HTTP dependency exists yet.
6. Existing MCP tool names and semantics remain intact and `ALL_TOOL_NAMES` contains exactly 55 tools.
7. The long-lived search -> write regression remains fixed.
8. CORE and MCP test suites, coverage gates, Ruff, formatting, mypy, source-size checks, and repository invariants all pass.
9. The real `data/2126/story.db`, Tunnel profile, and ChatGPT Connector configuration were not modified.
10. The repository is ready for Phase B to add `API/` without moving domain logic again.

## Plan Self-Review

- **Spec coverage:** Phase A spec requirements are covered: CORE extraction, migrations moved unchanged, temporary CORE-direct MCP, dependency direction, SQLite lifecycle preservation, tests/CI, and no real DB cutover.
- **Scope:** API endpoints, `project_id`, project registry, React, TipTap, and structured draft migration 005 are intentionally excluded and belong to later phase plans.
- **Type consistency:** `DatabaseConfig`, `open_database`, `default_migration_dir`, `initialize_work`, existing service/repository names, and `create_server` are used consistently across tasks.
- **Placeholder scan:** No implementation step relies on `TBD`, unspecified validation, or an undefined neighboring interface.
