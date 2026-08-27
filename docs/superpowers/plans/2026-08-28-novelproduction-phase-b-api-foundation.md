# NovelProduction Phase B API Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the shared FastAPI `/api/v1` backend, multi-project registry, request-scoped SQLite access, complete Phase 1–3 HTTP surface, and initial derived WEBUI views without changing the existing MCP tool interface or touching the real production story database.

**Architecture:** `API/` is a transport/orchestration package that depends on `novel_core`; it does not own story SQL or duplicate domain validation. Every project-scoped request resolves an immutable `project_id`, opens one SQLite connection through CORE, constructs CORE services on that connection, executes the request, and closes the connection. Project discovery/creation/archive is filesystem metadata around `data/<project_id>/story.db`; MCP remains CORE-direct during Phase B and is converted to HTTP only in Phase C.

**Tech Stack:** Python 3.10+ runtime, Python 3.13 CI/type-check target, FastAPI, Pydantic v2, Uvicorn, stdlib `sqlite3` through `novel_core`, setuptools, uv, pytest, httpx/FastAPI TestClient, Ruff, mypy, pre-commit.

**Spec:** `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

**Tracking:** Issue #8, parent Epic #6.

## Global Constraints

- Base the implementation on the latest `origin/main`; the reviewed Phase A + invariant-fix baseline is merge commit `0b4bd432771c9a9cbb8f30870511df1aec9ae6f2`.
- Phase B adds `API/` but **does not** convert MCP to HTTP. Existing MCP remains CORE-direct until Phase C.
- Do not change any of the 55 existing MCP tool names, input schemas, output semantics, or stdio behavior in Phase B.
- Do not add `project_id` to MCP tools in Phase B.
- Do not add `project_select` or any hidden current-project state.
- Do not add WEBUI/React/Vite/TipTap code in Phase B.
- Do not add migration `005`; migrations `001`–`004` remain byte/blob-identical and the existing Phase A invariant must stay green.
- Do not modify, initialize, migrate, delete, replace, vacuum, repair, or seed the real `data/2126/story.db` or any other stable/production DB during implementation/tests.
- All API tests must use temporary data roots and temporary story databases.
- All story writes go through CORE services. API route handlers must not issue story SQL directly.
- CORE continues to own SQLite lifecycle, migrations, repositories, services, transaction behavior, version checks, and domain validation.
- Each project-scoped HTTP request uses one project-specific SQLite connection and closes it at request completion; do not share a mutable connection across unrelated requests.
- Preserve `PRAGMA foreign_keys = ON`, WAL, `busy_timeout = 5000`, explicit short transactions, and optimistic concurrency.
- Preserve the search -> write regression fix.
- API success responses for project-scoped operations always include the addressed `project_id`.
- API errors use one structured contract under `/api/v1`; no HTML errors for API paths.
- Project discovery is based on immediate `data/*/story.db`; the directory name is immutable `project_id`.
- Project IDs are lowercase ASCII letters/digits/hyphens only, 1–64 characters, no leading/trailing hyphen, no traversal, slash, whitespace, or Unicode lookalikes.
- `project.json` contains only outer metadata: `project_id`, `status`, `created_at`, `updated_at`.
- Initial project statuses are exactly `active` and `archived`.
- Archived projects are omitted from normal project lists but remain fully readable/writable when explicitly addressed.
- Do not expose project deletion.
- Missing `project.json` must not make an existing `story.db` disappear from discovery; synthesize active metadata in memory and mark the metadata state as missing. Do not write metadata merely by listing.
- Malformed/mismatched `project.json` must not silently hide the story DB; keep the project discoverable as degraded metadata and do not auto-rewrite it on read.
- Project creation is staged under the data root and finalized by same-filesystem rename only after migrations, work initialization, integrity verification, and metadata write succeed.
- Default API bind is `0.0.0.0:8765`; the port is configurable. Do not silently choose another port when binding fails.
- Initial deployment is trusted-LAN only: no authentication/user system and no direct-public-Internet support.
- Development CORS may allow one configured Vite origin (normally `http://localhost:5173`); do not enable wildcard production CORS.
- FastAPI static WEBUI serving is Phase D. Phase B may run API-only when no frontend build exists.
- Issue #5 and Phase 4 continuity/inconsistency work remain out of scope.

---

## File Structure After Phase B

```text
API/
├─ pyproject.toml
├─ src/novel_api/
│  ├─ __init__.py
│  ├─ app.py                  # app factory + router registration
│  ├─ cli.py                  # novel-api entry point, host/port/data-root
│  ├─ config.py               # immutable runtime settings
│  ├─ dependencies.py         # registry/project request dependencies
│  ├─ errors.py               # common API error contract/mappers
│  ├─ project_registry.py     # discovery/create/archive filesystem logic
│  ├─ serialization.py        # JSON-safe dataclass/tuple conversion helpers
│  ├─ service_container.py    # per-connection CORE service composition
│  ├─ routes/
│  │  ├─ health.py
│  │  ├─ projects.py
│  │  ├─ work.py
│  │  ├─ world.py
│  │  ├─ timeline.py
│  │  ├─ characters.py
│  │  ├─ canon.py
│  │  ├─ narrative.py
│  │  ├─ information.py
│  │  ├─ authoring.py
│  │  └─ views.py
│  └─ schemas/
│     ├─ common.py
│     ├─ projects.py
│     ├─ work.py
│     ├─ world.py
│     ├─ timeline.py
│     ├─ characters.py
│     ├─ canon.py
│     ├─ narrative.py
│     ├─ information.py
│     └─ authoring.py
└─ tests/
   ├─ conftest.py
   ├─ test_health.py
   ├─ test_projects.py
   ├─ test_project_atomicity.py
   ├─ test_request_connections.py
   ├─ test_errors.py
   ├─ test_phase1_api.py
   ├─ test_phase2_api.py
   ├─ test_phase3_api.py
   ├─ test_views.py
   └─ test_multi_project_e2e.py

CORE/
└─ src/novel_core/
   ├─ database.py             # add integrity assertion helper only
   └─ errors.py               # add DatabaseIntegrityError only if needed

.github/workflows/mcp-ci.yml  # add API job; keep CORE/MCP/invariants
MCP/scripts/check_source_size.py
README.md
```

The exact route/schema split may be adjusted only to satisfy existing source-size rules; dependency direction and endpoint semantics below must not change.

---

### Task 1: Create the installable API package, settings, app factory, health endpoint, and CLI

**Files:**
- Create: `API/pyproject.toml`
- Create: `API/src/novel_api/__init__.py`
- Create: `API/src/novel_api/config.py`
- Create: `API/src/novel_api/app.py`
- Create: `API/src/novel_api/cli.py`
- Create: `API/src/novel_api/routes/__init__.py`
- Create: `API/src/novel_api/routes/health.py`
- Create: `API/tests/test_health.py`
- Create: `API/tests/test_cli.py`

**Interfaces:**
- Produces: `novel_api.config.ApiSettings`
- Produces: `novel_api.app.create_app(settings: ApiSettings) -> FastAPI`
- Produces: `novel_api.cli.main(argv: list[str] | None = None) -> None`
- Produces: `GET /api/v1/health`
- Consumes: `novel-production-core` as an editable local package during repository development.

- [ ] **Step 1: Create API package metadata**

Use the same packaging/quality conventions as CORE/MCP:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "novel-production-api"
version = "0.1.0"
description = "NovelProduction shared FastAPI backend"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.116,<1.0",
    "novel-production-core",
    "pydantic>=2.11,<3.0",
    "uvicorn>=0.35,<1.0",
]

[tool.uv.sources]
novel-production-core = { path = "../CORE", editable = true }

[project.scripts]
novel-api = "novel_api.cli:main"

[dependency-groups]
dev = [
    "httpx>=0.28,<1.0",
    "mypy>=1.18.0",
    "pre-commit>=4.3.0",
    "pytest>=8.4.0",
    "pytest-cov>=7.0.0",
    "ruff>=0.12.0",
]

[tool.setuptools]
package-dir = {"" = "src" }

[tool.setuptools.packages.find]
where = ["src"]

[tool.mypy]
python_version = "3.13"
strict = true

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src/novel_api"]

[tool.coverage.report]
fail_under = 80
show_missing = true

[tool.ruff]
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

If dependency resolution requires newer compatible minimums at implementation time, update only the minimums necessary and record the reason in the PR; do not perform unrelated dependency churn.

- [ ] **Step 2: Write failing health/settings tests**

`API/tests/test_health.py` must construct an app with a temporary data root and assert exactly:

```python
def test_health_is_api_only_and_does_not_require_a_project(tmp_path: Path) -> None:
    app = create_app(ApiSettings(data_root=tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "v1"}
```

`API/tests/test_cli.py` must assert the parser defaults to host `0.0.0.0`, port `8765`, and accepts explicit `--host`, `--port`, and `--data-root`.

Run before implementation:

```bash
cd API
uv sync --all-groups
uv run pytest tests/test_health.py tests/test_cli.py -q
```

Expected: FAIL because `novel_api` app/settings/CLI are not implemented.

- [ ] **Step 3: Implement immutable runtime settings**

Use an immutable dataclass; do not add `pydantic-settings` solely for configuration:

```python
@dataclass(frozen=True, slots=True)
class ApiSettings:
    data_root: Path
    host: str = "0.0.0.0"
    port: int = 8765
    dev_cors_origin: str | None = None
```

Resolution rules for the CLI:

1. explicit CLI argument;
2. `NOVEL_DATA_ROOT`, `NOVEL_API_HOST`, `NOVEL_API_PORT`, `NOVEL_DEV_CORS_ORIGIN` when present;
3. repository checkout `data/` when the package can positively identify the checkout root containing both `CORE/` and `MCP/`;
4. otherwise `Path.cwd() / "data"`.

Never guess a different port if `8765` is occupied.

- [ ] **Step 4: Implement app factory and health route**

The app factory must store settings on `app.state.settings`, install only explicit routers, and return the FastAPI instance. The health endpoint must not open/discover any story DB.

Initial route:

```python
@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "api_version": "v1"}
```

Mount the router under `/api/v1` from `create_app`.

- [ ] **Step 5: Implement CLI entry point**

Use `argparse`; construct `ApiSettings`, construct the app object, and call `uvicorn.run(app, host=settings.host, port=settings.port)`. Uvicorn bind failure must propagate/exit rather than selecting another port.

- [ ] **Step 6: Run tests/static checks and commit**

```bash
cd API
uv run pytest tests/test_health.py tests/test_cli.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: PASS.

Commit:

```bash
git add API
git commit -m "feat: add FastAPI application foundation"
```

---

### Task 2: Add CORE integrity verification and the filesystem project registry

**Files:**
- Modify: `CORE/src/novel_core/database.py`
- Modify: `CORE/src/novel_core/errors.py` only if adding `DatabaseIntegrityError`
- Add/modify CORE tests for integrity verification
- Create: `API/src/novel_api/project_registry.py`
- Create: `API/src/novel_api/schemas/projects.py`
- Create: `API/src/novel_api/routes/projects.py`
- Create: `API/tests/conftest.py`
- Create: `API/tests/test_projects.py`
- Create: `API/tests/test_project_atomicity.py`

**Interfaces:**
- Produces: `novel_core.database.assert_database_integrity(connection: sqlite3.Connection) -> None`
- Produces: `ProjectRegistry(data_root: Path)` with `list`, `get`, `create`, `set_status`
- Produces: project routes under `/api/v1/projects`
- Consumes: `novel_core.initialization.initialize_work`, `open_database`, `WorkService`.

- [ ] **Step 1: Write failing CORE integrity tests**

Add a test that migrates/initializes a temp DB, opens it through CORE, runs `assert_database_integrity(connection)`, and passes. Add a unit case that makes the helper observe a non-`ok` integrity result via a test double and raises a CORE-owned error rather than returning a false success.

The implementation must execute exactly `PRAGMA integrity_check` in CORE, not in API.

- [ ] **Step 2: Implement `assert_database_integrity` in CORE**

The helper must treat the one-row value `ok` as success and all other/no-result states as failure. If a dedicated exception is added, make it a CORE exception and do not change existing exception classes/strings.

Run:

```bash
cd CORE
uv run pytest -W error
```

Expected: existing 134+ tests plus the new integrity tests PASS.

- [ ] **Step 3: Define project metadata and validation**

Use these stable rules:

```text
project_id regex: ^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$
length: 1..64
status: active | archived
```

`project.json` written by the API is exactly conceptually:

```json
{
  "project_id": "winter-tokyo",
  "status": "active",
  "created_at": "2026-08-28T00:00:00Z",
  "updated_at": "2026-08-28T00:00:00Z"
}
```

Use UTC timestamps with a `Z` suffix. `project_id` is immutable.

Project response metadata includes a derived `metadata_state` with values `ok`, `missing`, `invalid`. This state is not persisted in `project.json`.

- [ ] **Step 4: Write failing discovery tests**

Tests must cover:

1. `data/alpha/story.db` created via CORE but no `project.json` -> listed as active with `metadata_state="missing"`;
2. default list hides an archived project;
3. `include_archived=true` includes it;
4. malformed JSON or mismatched `project_id` does not hide `story.db`; it is discoverable with `metadata_state="invalid"`;
5. a directory without `story.db` is not a project;
6. nested staging DBs under `data/.staging/<token>/story.db` are not immediate `data/*/story.db` projects;
7. explicit get of unknown valid ID raises project-not-found;
8. traversal/Unicode/whitespace IDs are rejected before filesystem resolution.

- [ ] **Step 5: Implement `ProjectRegistry.list` and `get`**

Discovery iterates only immediate child directories containing `story.db`. Never discover recursively.

Missing metadata behavior:

```text
story.db exists + no project.json
=> status active in memory
=> created_at/updated_at null in API summary
=> metadata_state missing
=> no file write
```

Invalid metadata behavior:

```text
story.db exists + malformed/mismatched project.json
=> keep project visible
=> status active in memory
=> metadata_state invalid
=> no file rewrite
```

Because archive is organizational, falling back to active for broken metadata is acceptable; it must never be treated as an authorization boundary.

- [ ] **Step 6: Write failing atomic project-creation tests**

Cover:

- explicit valid ID creates `story.db`, migrations 001–004, one `works` row, and valid `project.json`;
- omitted ID generates `project-YYYYMMDD-HHMMSS`, with `-2`, `-3`, ... suffix on collision;
- title is not translated or slugified into the generated ID;
- duplicate explicit ID returns a conflict and leaves the existing project untouched;
- injected failure during initialize/integrity/metadata write leaves no `data/<project_id>` directory;
- staging directory is cleaned after failure;
- project creation never touches any path outside the supplied temp data root.

- [ ] **Step 7: Implement staged creation**

Creation order is fixed:

```text
validate/generate project_id
-> acquire per-project exclusive creation lock under data/.locks/
-> create data/.staging/<uuid>/
-> initialize_work(staging/story.db, working_title=...)
-> open through CORE and assert_database_integrity
-> write staging/project.json
-> verify final data/<project_id> is still absent
-> same-filesystem rename staging dir to final dir
-> release lock
```

Use an exclusive lock file (`os.open` with `O_CREAT | O_EXCL`) or an equivalently tested cross-request mechanism. Never replace an existing final project directory.

- [ ] **Step 8: Implement atomic archive/restore metadata updates**

`PATCH /api/v1/projects/{project_id}` accepts only:

```json
{"status": "active"}
```

or:

```json
{"status": "archived"}
```

Write `project.json` through a temporary file in the same directory followed by `os.replace`. If metadata was missing/invalid, this explicit update repairs it and establishes fresh `created_at` when no valid prior value exists.

Archived projects remain addressable and writable.

- [ ] **Step 9: Implement project HTTP routes**

Required routes:

```text
GET   /api/v1/projects?include_archived=false
POST  /api/v1/projects
GET   /api/v1/projects/{project_id}
PATCH /api/v1/projects/{project_id}
```

Create input:

```json
{
  "working_title": "2126",
  "project_id": "2126"
}
```

`project_id` is optional; `working_title` is required/non-empty.

Project summaries include at least: `project_id`, `status`, `metadata_state`, `working_title`, `created_at`, `updated_at`. Read `working_title` from `story.db` through CORE/`WorkService`; never duplicate it into `project.json`.

If one discovered DB cannot be opened/read, list it with a degraded/null title rather than silently deleting the project from the list; explicit project data routes may then return a structured server/database error.

- [ ] **Step 10: Run focused tests and commit**

```bash
cd CORE
uv run pytest -W error
cd ../API
uv run pytest tests/test_projects.py tests/test_project_atomicity.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Commit:

```bash
git add CORE API
git commit -m "feat: add atomic multi-project registry"
```

---

### Task 3: Add request-scoped project connections and CORE service composition

**Files:**
- Create: `API/src/novel_api/service_container.py`
- Create: `API/src/novel_api/dependencies.py`
- Create: `API/tests/test_request_connections.py`

**Interfaces:**
- Produces: `ServiceContainer` containing the same current CORE services MCP wires today.
- Produces: `ProjectRequestContext(project_id, project, connection, services)`.
- Produces: FastAPI dependency that yields exactly one context/connection per project-scoped request.

- [ ] **Step 1: Implement a typed service container factory**

Compose the current services on one connection:

```text
WorkService
WorldFactService
TimelineService
CharacterService
RelationshipService
CanonService
SearchService
NarrativeService
CharacterStateService
InformationService
DisclosureService
KnowledgeService
EpisodeReferenceService
DraftService
OutlineService
ContextService
```

Do not move business logic into the container.

- [ ] **Step 2: Write failing connection-lifecycle tests**

Tests must prove:

- two separate HTTP requests for the same project receive different SQLite connection objects;
- one request uses one connection for all services in its container;
- the connection is closed after response completion;
- an exception path also closes the connection;
- archived project lookup still yields a normal connection;
- unknown project fails before any DB path is opened.

Use instrumentation/test doubles around `novel_core.database.open_database`; never inspect the real DB.

- [ ] **Step 3: Implement the project dependency**

The dependency flow is:

```text
path project_id
-> ProjectRegistry.get(project_id)
-> DatabaseConfig(project.story_db, default_migration_dir())
-> open_database(config)
-> build ServiceContainer(connection)
-> yield ProjectRequestContext
-> close in finally
```

Do not cache the SQLite connection in app state, registry state, thread-local state, or a global.

- [ ] **Step 4: Add search -> write HTTP regression**

On a temp project:

1. create a world fact through API setup/CORE;
2. call world-fact search request;
3. issue a subsequent write request;
4. assert the write succeeds and no stale transaction state crosses requests.

This supplements, not replaces, the CORE regression.

- [ ] **Step 5: Run tests and commit**

```bash
cd API
uv run pytest tests/test_request_connections.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Commit:

```bash
git add API
git commit -m "feat: add request scoped project services"
```

---

### Task 4: Implement the common success/error contract and conflict snapshots

**Files:**
- Create: `API/src/novel_api/schemas/common.py`
- Create: `API/src/novel_api/serialization.py`
- Create: `API/src/novel_api/errors.py`
- Modify: `API/src/novel_api/app.py`
- Create: `API/tests/test_errors.py`

**Interfaces:**
- Produces project success envelope: `{"project_id": <id>, "data": ...}`.
- Produces API error envelope: `{"error": {"code", "message", "project_id", "details"}}`.
- Produces helper for version conflicts that can attach a safe latest-resource snapshot.

- [ ] **Step 1: Define stable response models**

Use a generic Pydantic v2 model:

```python
T = TypeVar("T")

class ProjectEnvelope(BaseModel, Generic[T]):
    project_id: str
    data: T
```

CORE stdlib dataclasses may be used directly as `T`; avoid duplicating every CORE record into transport-only response classes.

Define errors conceptually as:

```python
class ApiError(BaseModel):
    code: str
    message: str
    project_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

class ApiErrorEnvelope(BaseModel):
    error: ApiError
```

- [ ] **Step 2: Write failing mapping tests**

Test exact HTTP/code behavior:

```text
Pydantic/FastAPI request validation -> 400 VALIDATION_ERROR
CORE ValidationError / ValueError     -> 400 VALIDATION_ERROR
ProjectNotFound                       -> 404 PROJECT_NOT_FOUND
CORE *NotFoundError                   -> 404 NOT_FOUND
CORE WorkScopeError                   -> 404 NOT_FOUND
VersionConflictError                  -> 409 VERSION_CONFLICT
OrderConflictError                    -> 409 ORDER_CONFLICT
RelationshipIntegrity/IntegrityError  -> 409 DEPENDENCY_CONFLICT
Canon policy conflicts                -> 409 DEPENDENCY_CONFLICT
locked sqlite OperationalError        -> 503 DATABASE_BUSY
unexpected exception                  -> 500 INTERNAL_ERROR
```

For domain-specific errors normalized to a common code, preserve the original CORE class/code in `details.domain_code` when useful; clients must still key primarily on the common API `code`.

Never expose raw SQLite error text or traceback in the JSON body.

- [ ] **Step 3: Implement one exception-handler installation function**

`create_app` installs handlers for:

- `RequestValidationError`;
- project-registry API exceptions;
- CORE base/domain exceptions;
- `sqlite3.Error`;
- fallback `Exception`.

Log server-side unexpected errors; return safe client messages.

- [ ] **Step 4: Add reusable VERSION_CONFLICT context helper**

For update/reorder/save routes that know `expected_version`/parent and can safely re-read the target after the CORE service has rolled back, attach:

```json
{
  "entity_type": "episode",
  "entity_id": 14,
  "expected_version": 4,
  "current_version": 5,
  "current_resource": {"...": "latest record"}
}
```

The global fallback handler may return a smaller `VERSION_CONFLICT` when a safe latest snapshot is not available. Do not parse version numbers from exception strings.

- [ ] **Step 5: Run tests and commit**

```bash
cd API
uv run pytest tests/test_errors.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Commit:

```bash
git add API
git commit -m "feat: add shared API error contract"
```

---

### Task 5: Expose the complete Phase 1 HTTP surface

**Files:**
- Create: `API/src/novel_api/schemas/work.py`
- Create: `API/src/novel_api/schemas/world.py`
- Create: `API/src/novel_api/schemas/timeline.py`
- Create: `API/src/novel_api/schemas/characters.py`
- Create: `API/src/novel_api/schemas/canon.py`
- Create: `API/src/novel_api/routes/work.py`
- Create: `API/src/novel_api/routes/world.py`
- Create: `API/src/novel_api/routes/timeline.py`
- Create: `API/src/novel_api/routes/characters.py`
- Create: `API/src/novel_api/routes/canon.py`
- Modify: `API/src/novel_api/app.py`
- Create: `API/tests/test_phase1_api.py`

**Interfaces:**
- Consumes only the `ProjectRequestContext.services` CORE services.
- Produces HTTP equivalents of all 23 Phase 1 MCP operations.

- [ ] **Step 1: Define the exact Phase 1 route inventory**

Implement all routes below:

```text
GET   /api/v1/projects/{project_id}/work
PATCH /api/v1/projects/{project_id}/work

POST  /api/v1/projects/{project_id}/world-facts
GET   /api/v1/projects/{project_id}/world-facts/{fact_id}
PATCH /api/v1/projects/{project_id}/world-facts/{fact_id}
GET   /api/v1/projects/{project_id}/world-facts/search?query=&limit=20

POST  /api/v1/projects/{project_id}/timeline/events
GET   /api/v1/projects/{project_id}/timeline/events/{event_id}
PATCH /api/v1/projects/{project_id}/timeline/events/{event_id}
GET   /api/v1/projects/{project_id}/timeline/events/search?query=&limit=20
GET   /api/v1/projects/{project_id}/timeline/range?start=&end=&limit=20
POST  /api/v1/projects/{project_id}/timeline/events/{event_id}/move
POST  /api/v1/projects/{project_id}/timeline/relations

POST  /api/v1/projects/{project_id}/characters
GET   /api/v1/projects/{project_id}/characters/{character_id}
PATCH /api/v1/projects/{project_id}/characters/{character_id}
GET   /api/v1/projects/{project_id}/characters/search?query=&limit=20

POST  /api/v1/projects/{project_id}/relationships
PATCH /api/v1/projects/{project_id}/relationships/{relationship_id}
GET   /api/v1/projects/{project_id}/relationships?character_id=&limit=20

POST  /api/v1/projects/{project_id}/canon/status
GET   /api/v1/projects/{project_id}/canon/decisions/{decision_id}
GET   /api/v1/projects/{project_id}/canon/decisions/search?query=&limit=20
```

These correspond exactly to Phase 1 tool behavior; do not silently add different domain semantics.

- [ ] **Step 2: Define request schemas with the existing tool fields**

Transport schemas must contain these fields:

```text
WorkUpdate:
  working_title, expected_version, genre?, premise?, themes_json?, description?, production_status?

WorldFactCreate:
  statement, valid_from?, valid_to?, topic_key?, category="general", title?, details_json={}, importance=0
WorldFactUpdate:
  statement, expected_version, reason?, topic_key?, category?, title?, details_json?, valid_from?, valid_to?, importance?

TimelineParticipant:
  character_id, role
TimelineEventCreate:
  title, event_date?, participants?, event_key?, time_start?, time_end?, date_precision?,
  date_display?, description="", category="general", location_world_fact_id?,
  cause_summary="", consequence_summary="", importance=0
TimelineEventUpdate:
  expected_version, title?, new_date?, participants?, reason?, time_start?, time_end?,
  date_precision?, date_display?, description?, category?, location_world_fact_id?,
  cause_summary?, consequence_summary?, importance?
TimelineMove:
  expected_version, new_date, reason?
TimelineRelationCreate:
  source_id, target_id, relation_type

CharacterCreate:
  display_name, character_key?, entity_type="human", description="", birth_date?, death_date?,
  physical_description="", occupation="", core_beliefs="", goals="", fears="",
  personality="", speech_style="", ai_attitude="", genetic_modification_attitude="",
  private_notes="", profile_json={}
CharacterUpdate:
  expected_version, display_name?, description?, reason?, character_key?, entity_type?,
  birth_date?, death_date?, physical_description?, occupation?, core_beliefs?, goals?, fears?,
  personality?, speech_style?, ai_attitude?, genetic_modification_attitude?, private_notes?, profile_json?

RelationshipCreate:
  source_character_id, target_character_id, relationship_type, description="",
  valid_from_episode_id?, valid_to_episode_id?
RelationshipUpdate:
  expected_version, relationship_type, description?, reason?, valid_from_episode_id?,
  valid_to_episode_id?, clear_valid_from=false, clear_valid_to=false

CanonStatusSet:
  entity_type, entity_id, target_status, expected_version, reason?
```

Use Pydantic for transport shape/bounds but leave domain policy to CORE. JSON-valued transport fields may accept real JSON values; convert them to the compact string form CORE currently expects only at the route/adapter boundary. A helper equivalent to current MCP `json_text` is allowed in `serialization.py`.

- [ ] **Step 3: Write table-driven Phase 1 API tests before route implementation**

At minimum verify:

- each route exists and returns project envelope with correct `project_id`;
- create/get/update/search happy paths;
- Japanese world-fact/character search behavior remains intact;
- timeline range/move/relation behavior;
- relationship temporal validation maps to structured API error;
- canon reason/policy errors are structured;
- stale work/world/character update yields HTTP 409 and latest snapshot where implemented;
- project A IDs never resolve against project B DB.

- [ ] **Step 4: Implement thin route handlers**

Handlers may transform HTTP request models into existing CORE service arguments, call the service, and wrap the returned value. They must not recreate CORE validation, call repository SQL directly, or commit/rollback themselves.

- [ ] **Step 5: Run Phase 1 tests and commit**

```bash
cd API
uv run pytest tests/test_phase1_api.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Commit:

```bash
git add API
git commit -m "feat: expose Phase 1 HTTP API"
```

---

### Task 6: Expose the complete Phase 2 HTTP surface

**Files:**
- Create: `API/src/novel_api/schemas/narrative.py`
- Create: `API/src/novel_api/schemas/information.py`
- Create: `API/src/novel_api/routes/narrative.py`
- Create: `API/src/novel_api/routes/information.py`
- Modify: `API/src/novel_api/app.py`
- Create: `API/tests/test_phase2_api.py`

**Interfaces:**
- Produces HTTP equivalents of all 27 Phase 2 MCP operations.

- [ ] **Step 1: Implement the exact narrative/reference/state routes**

```text
POST  /api/v1/projects/{project_id}/chapters
GET   /api/v1/projects/{project_id}/chapters
PATCH /api/v1/projects/{project_id}/chapters/{chapter_id}
POST  /api/v1/projects/{project_id}/chapters/{chapter_id}/reorder

POST  /api/v1/projects/{project_id}/chapters/{chapter_id}/episodes
GET   /api/v1/projects/{project_id}/chapters/{chapter_id}/episodes
GET   /api/v1/projects/{project_id}/episodes/{episode_id}
PATCH /api/v1/projects/{project_id}/episodes/{episode_id}
POST  /api/v1/projects/{project_id}/episodes/{episode_id}/reorder

POST  /api/v1/projects/{project_id}/episodes/{episode_id}/scenes
GET   /api/v1/projects/{project_id}/episodes/{episode_id}/scenes
GET   /api/v1/projects/{project_id}/scenes/{scene_id}
PATCH /api/v1/projects/{project_id}/scenes/{scene_id}
POST  /api/v1/projects/{project_id}/scenes/{scene_id}/reorder

POST   /api/v1/projects/{project_id}/episodes/{episode_id}/references
DELETE /api/v1/projects/{project_id}/episodes/{episode_id}/references/{reference_type}/{target_id}
GET    /api/v1/projects/{project_id}/episodes/{episode_id}/references?reference_type=

PUT /api/v1/projects/{project_id}/characters/{character_id}/states/{episode_id}
GET /api/v1/projects/{project_id}/characters/{character_id}/states/{episode_id}
GET /api/v1/projects/{project_id}/characters/{character_id}/states
```

The reference DELETE is only the already-existing `episode_reference_remove` semantic; it is not general entity deletion and must not be expanded.

- [ ] **Step 2: Implement the exact information/disclosure/knowledge routes**

```text
POST  /api/v1/projects/{project_id}/information
GET   /api/v1/projects/{project_id}/information/{information_item_id}
PATCH /api/v1/projects/{project_id}/information/{information_item_id}
GET   /api/v1/projects/{project_id}/information/search?query=&limit=20

PUT /api/v1/projects/{project_id}/information/{information_item_id}/reader-disclosure

PUT /api/v1/projects/{project_id}/characters/{character_id}/knowledge/{information_item_id}
GET /api/v1/projects/{project_id}/characters/{character_id}/knowledge?episode_id=
```

- [ ] **Step 3: Define exact Phase 2 request fields**

```text
ChapterCreate:
  title, summary="", purpose="", production_status="planned", canon_status="draft"
ChapterUpdate:
  expected_version, title?, summary?, purpose?, production_status?, canon_status?, reason?
Reorder:
  target_position, expected_version

EpisodeCreate:
  title, summary="", purpose="", foreshadowing_notes?, production_status="planned", canon_status="draft"
EpisodeUpdate:
  expected_version, title?, summary?, purpose?, foreshadowing_notes?, production_status?, canon_status?, reason?

SceneCreate:
  title, summary="", purpose="", production_status="planned", canon_status="draft"
SceneUpdate:
  expected_version, title?, summary?, purpose?, production_status?, canon_status?, reason?

EpisodeReferenceAdd:
  reference_type, target_id, role="participant"

CharacterStateSet:
  physical_state?, emotional_state?, beliefs_json?, location_world_fact_id?, state_json?, expected_version?

InformationCreate:
  statement, truth_status="uncertain", authoring_guard="", notes_json?, canon_status="draft", importance=0
InformationUpdate:
  expected_version, statement?, truth_status?, authoring_guard?, notes_json?, importance?, canon_status?, reason?

ReaderDisclosureSet:
  episode_id, expected_version?

CharacterKnowledgeSet:
  episode_id, knowledge_state, note="", expected_version?
```

Path IDs are not duplicated in request bodies unless the existing operation truly needs a distinct target ID.

- [ ] **Step 4: Write Phase 2 regression tests before implementation**

Cover all 27 operations at least once across table-driven/integration scenarios, including:

- chapter/episode/scene create/list/get/update/reorder;
- optimistic reorder conflict;
- reference add/list/remove;
- character state effective lookup/history;
- information create/get/update/search;
- disclosure set;
- character knowledge set/get;
- cross-project IDs fail closed;
- deprecated/canon guards preserve CORE behavior.

- [ ] **Step 5: Implement thin handlers and conflict snapshots**

For narrative update/reorder, re-read the current entity after `VersionConflictError` and attach `current_resource/current_version` through the Task 4 helper. Do not implement Issue #5 retirement semantics here; current list behavior remains unchanged.

- [ ] **Step 6: Run Phase 2 tests and commit**

```bash
cd API
uv run pytest tests/test_phase2_api.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Commit:

```bash
git add API
git commit -m "feat: expose Phase 2 HTTP API"
```

---

### Task 7: Expose the complete Phase 3 authoring HTTP surface

**Files:**
- Create: `API/src/novel_api/schemas/authoring.py`
- Create: `API/src/novel_api/routes/authoring.py`
- Modify: `API/src/novel_api/app.py`
- Create: `API/tests/test_phase3_api.py`

**Interfaces:**
- Produces HTTP equivalents of all 5 Phase 3 MCP operations.

- [ ] **Step 1: Define exact routes**

```text
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/outline
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/context
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/draft?revision=
POST /api/v1/projects/{project_id}/episodes/{episode_id}/drafts
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/drafts?limit=20
```

`GET .../draft` returns HTTP 200 with `data: null` when the CORE service returns no draft, preserving current service semantics.

- [ ] **Step 2: Define draft-save request**

```text
body: non-empty string
expected_parent_draft_id?: positive integer
source_agent?: 1..120 chars
change_summary: max 1000 chars, default ""
```

Do not add structured draft JSON in Phase B.

- [ ] **Step 3: Write Phase 3 tests**

Cover:

- outline and context outputs;
- context future/disclosure guards remain intact;
- draft absent -> `data: null`;
- first save, get, second save, history;
- stale `expected_parent_draft_id` -> 409 VERSION_CONFLICT with latest draft ID/resource when available;
- append-only history remains unchanged;
- cross-project episode IDs fail closed.

- [ ] **Step 4: Implement handlers and run tests**

```bash
cd API
uv run pytest tests/test_phase3_api.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

- [ ] **Step 5: Commit**

```bash
git add API
git commit -m "feat: expose Phase 3 authoring API"
```

---

### Task 8: Add initial read-only WEBUI aggregate views without alternate storage

**Files:**
- Create: `API/src/novel_api/routes/views.py`
- Add view response models to `API/src/novel_api/schemas/common.py` or a focused `schemas/views.py` if size requires
- Create: `API/tests/test_views.py`
- Modify: `API/src/novel_api/app.py`

**Interfaces:**
- Produces derived read-only views; all data comes from the same request-scoped CORE services.

- [ ] **Step 1: Add full outline view**

Route:

```text
GET /api/v1/projects/{project_id}/views/outline
```

Response data is deterministic hierarchy order:

```json
{
  "chapters": [
    {
      "chapter": {"...": "ChapterRecord"},
      "episodes": [
        {
          "episode": {"...": "EpisodeRecord"},
          "scenes": [{"...": "SceneRecord"}]
        }
      ]
    }
  ]
}
```

Construct using `NarrativeService.list_chapters`, `list_episodes`, and `list_scenes`. Do not query story tables from API.

- [ ] **Step 2: Add dashboard view**

Route:

```text
GET /api/v1/projects/{project_id}/views/dashboard
```

Return at least:

```text
work
chapter_count
episode_count
scene_count
```

Counts are derived from the same hierarchy read, not stored separately.

- [ ] **Step 3: Add episode aggregate view**

Route:

```text
GET /api/v1/projects/{project_id}/views/episodes/{episode_id}
```

Return:

```text
episode
scenes
episode_references
outline
context
latest_draft
recent_draft_history (limit 20)
```

A missing draft is represented as null. This view is read-only and must preserve the same context leakage/canon guards as the fine-grained context endpoint.

- [ ] **Step 4: Write deterministic view tests**

Build a temp project with two chapters/episodes/scenes in nontrivial order and verify ordered hierarchy, correct counts, project identity, and no writes/version changes caused by reading views.

- [ ] **Step 5: Run tests and commit**

```bash
cd API
uv run pytest tests/test_views.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Commit:

```bash
git add API
git commit -m "feat: add derived authoring API views"
```

---

### Task 9: Add multi-project/concurrency E2E coverage and LAN runtime guardrails

**Files:**
- Create: `API/tests/test_multi_project_e2e.py`
- Modify: `API/src/novel_api/app.py` for optional development CORS
- Modify: `README.md`

**Interfaces:**
- Proves the shared backend boundary is safe before Phase C points MCP at it.

- [ ] **Step 1: Write end-to-end multi-project isolation test**

Scenario:

1. create `alpha` and `beta` via `POST /projects`;
2. create a world fact/character/chapter in each so numeric IDs may collide;
3. read each by explicit project route;
4. verify `alpha` never returns `beta` content and vice versa;
5. verify every response carries the addressed `project_id`.

- [ ] **Step 2: Write optimistic-concurrency HTTP test**

Scenario:

1. GET work or episode at version N;
2. PATCH from client A with expected N -> success/version N+1;
3. PATCH from client B with expected N -> HTTP 409 VERSION_CONFLICT;
4. verify error details contain expected N, current N+1, and safe latest snapshot;
5. GET latest remains client A's version, proving no silent last-write-wins.

- [ ] **Step 3: Write archive semantics E2E test**

Scenario:

1. archive `alpha`;
2. default project list omits it;
3. `include_archived=true` returns it;
4. explicit GET work succeeds;
5. explicit PATCH work succeeds while archived;
6. restore active and default list returns it again.

- [ ] **Step 4: Add optional development CORS only**

When `dev_cors_origin` is non-null, configure exactly that origin for development browser requests. When null, install no broad CORS policy. Never use `*` with credentials.

- [ ] **Step 5: Document runtime boundary**

README must state:

```text
API default: 0.0.0.0:8765
LAN trusted only; no authentication
MCP remains CORE-direct during Phase B
Phase C will switch MCP to http://127.0.0.1:8765/api/v1
WEBUI static serving is not implemented until Phase D
```

Show an explicit temp/sandbox startup example for development; do not instruct Phase B verification to point at the stable `data/2126/story.db`.

- [ ] **Step 6: Run E2E and commit**

```bash
cd API
uv run pytest tests/test_multi_project_e2e.py -q
```

Commit:

```bash
git add API README.md
git commit -m "test: verify multi-project API isolation"
```

---

### Task 10: Integrate API quality gates into repository CI and verify the complete Phase B boundary

**Files:**
- Modify: `.github/workflows/mcp-ci.yml`
- Modify: `MCP/scripts/check_source_size.py` (or move to a shared root script only if the existing policy remains identical)
- Modify: `docs/superpowers/plans/2026-08-28-novelproduction-delivery-plan-index.md`
- Modify Issue #8/PR documentation as part of delivery

**Interfaces:**
- CI must independently verify CORE, API, MCP, and migration/tool invariants.

- [ ] **Step 1: Extend source-size coverage without relaxing limits**

The existing source-size policy must inspect:

```text
CORE/src
CORE/tests
API/src
API/tests
MCP/src
MCP/tests
```

Do not raise file-size thresholds just because API was added. Split oversized files by responsibility instead.

- [ ] **Step 2: Add an `api` GitHub Actions job**

Use Python 3.13 and run from `API/`:

```text
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_api --cov-report=term-missing
```

Keep existing `core`, `mcp`, and `invariants` jobs. Preserve installed CORE wheel smoke, exact migration blob checks, no-005 inventory, and MCP tool count 55.

- [ ] **Step 3: Add dependency-boundary invariants**

CI/tests must fail if:

```text
API imports novel_mcp or mcp
CORE imports novel_api / FastAPI / MCP
API route modules execute direct story SQL
migration 005 appears
MCP tool inventory differs from 55
```

`sqlite3` may appear in API error/type plumbing, but story `execute(...)` SQL belongs to CORE; enforce the meaningful boundary rather than a brittle blanket import ban.

- [ ] **Step 4: Run full local verification from a clean worktree**

Run all applicable commands:

```bash
cd CORE
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_core --cov-report=term-missing

cd ../API
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_api --cov-report=term-missing

cd ../MCP
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_mcp --cov-report=term-missing
uv run pre-commit run --all-files

cd ..
python MCP/scripts/check_source_size.py
git diff --check
git status --short
```

Also verify the current invariant logic still reports exactly migrations 001–004 with the canonical blobs and that `MCP/migrations` remains absent.

- [ ] **Step 5: Explicitly verify scope/safety before PR creation**

Confirm and report:

```text
real data/2126/story.db touched: NO
other stable story.db touched: NO
Tunnel changed: NO
ChatGPT Connector changed: NO
MCP HTTP cutover: NO
MCP tool schema changes: NO
MCP tool count: 55
migration 005: absent
WEBUI code: absent
```

- [ ] **Step 6: Update the delivery-plan index**

Change Phase B from “plan to be written” to:

```text
docs/superpowers/plans/2026-08-28-novelproduction-phase-b-api-foundation.md
```

Do not write Phase C implementation details yet; its plan must target the API contract actually merged from Phase B.

- [ ] **Step 7: Push and open a Draft PR**

Suggested title:

```text
[Issue #8] Add shared FastAPI v1 backend and project registry
```

PR body must include:

- `Refs #8` / parent #6;
- API architecture and endpoint coverage summary;
- project registry/discovery/create/archive semantics;
- one-request/one-connection evidence;
- error contract and conflict evidence;
- Phase 1–3 endpoint coverage count;
- aggregate views implemented;
- CORE/API/MCP test counts and coverage;
- CI results;
- explicit statement that production DB/Tunnel/Connector were untouched;
- explicit statement that MCP remains CORE-direct and Phase C is not implemented.

Do not merge the PR. Return it for review.

---

## Phase B Endpoint Coverage Checklist

A reviewer must be able to map every existing MCP operation to at least one HTTP endpoint before Phase B is accepted.

```text
Phase 1 (23)
  work_get / work_update
  world_fact_create / update / get / search
  timeline_event_create / update / get / search
  timeline_range / timeline_move / timeline_relation_create
  character_create / update / get / search
  relationship_create / update / search
  canon_status_set / canon_decision_get / canon_decision_search

Phase 2 (27)
  chapter_create / update / reorder / list
  episode_create / update / get / reorder / list
  scene_create / update / get / reorder / list
  episode_reference_add / remove / list
  character_state_set / get / history
  information_create / update / get / search
  reader_disclosure_set
  character_knowledge_set / get

Phase 3 (5)
  episode_outline_get
  episode_context
  episode_draft_get
  episode_draft_save
  episode_draft_history

Total existing project-data operations covered by HTTP: 55
```

Project-management routes are additional and are not counted in the 55.

## Phase B Exit State

After the Phase B PR is reviewed and merged:

```text
Browser/future WEBUI ─HTTP─┐
                            ↓
                         FastAPI ──> CORE ──> project SQLite DB

MCP ───────────────────────> CORE ──> configured SQLite DB
        (temporary Phase B state only)
```

Phase C then removes the lower direct MCP→CORE runtime path and adds explicit `project_id` to MCP tools. Do not pre-implement that cutover in Phase B.
