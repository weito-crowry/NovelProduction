# NovelProduction Phase B API Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the shared FastAPI `/api/v1` backend, multi-project registry, request-scoped SQLite execution, complete Phase 1–3 HTTP surface, and initial derived WEBUI views without changing the existing MCP tool interface or touching the real production story database.

**Architecture:** `API/` is a transport/orchestration package that depends on `novel_core`; it does not own story SQL or duplicate domain validation. A project-scoped request resolves immutable `project_id` first, then the synchronous route handler opens one CORE SQLite connection inside that same handler/thread, constructs CORE services, performs all reads/writes for the request, and closes the connection before returning. Project discovery/create/archive is filesystem metadata around `data/<project_id>/story.db`. MCP remains CORE-direct during Phase B and is converted to HTTP only in Phase C.

**Tech Stack:** Python 3.10+ runtime, Python 3.13 CI/type-check target, FastAPI, Pydantic v2, Uvicorn, stdlib `sqlite3` through `novel_core`, setuptools, uv, pytest, httpx/FastAPI TestClient, Ruff, mypy, pre-commit.

**Spec:** `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

**Tracking:** Issue #8, parent Epic #6.

## Global Constraints

- Base work on latest `origin/main`; the reviewed Phase A + invariant-fix baseline is `0b4bd432771c9a9cbb8f30870511df1aec9ae6f2`.
- Phase B adds `API/` but does **not** convert MCP to HTTP. Existing MCP remains CORE-direct until Phase C.
- Do not change any of the 55 existing MCP tool names, input schemas, output semantics, or stdio behavior.
- Do not add `project_id` to MCP tools and do not add `project_select` hidden state.
- Do not add WEBUI/React/Vite/TipTap code.
- Do not add migration `005`; migrations `001`–`004` remain exact canonical blobs and existing invariant checks remain green.
- Do not modify, initialize, migrate, delete, replace, vacuum, repair, seed, or hash-lock the real `data/2126/story.db` or any stable/production DB during implementation/tests.
- All API tests use temporary data roots and temporary story DBs.
- All story writes go through CORE services. API routes do not issue story SQL directly.
- CORE owns SQLite lifecycle, migrations, repositories, services, transaction behavior, version checks, and domain validation.
- Every project-scoped route uses exactly one project SQLite connection per request and closes it before returning.
- Do **not** create a SQLite connection in an async/sync FastAPI dependency and then use it in a different execution thread. Project DB routes are synchronous `def` handlers; the connection is opened/used/closed inside the same handler call through a local context manager.
- Do not change CORE to `check_same_thread=False` merely to accommodate FastAPI; preserve the current SQLite connection behavior.
- Preserve `PRAGMA foreign_keys = ON`, WAL, `busy_timeout = 5000`, explicit short transactions, optimistic concurrency, and search -> write safety.
- Every project-scoped success response includes the addressed `project_id`.
- API failures use one JSON error contract under `/api/v1`; no HTML error body for API failures.
- Project discovery is immediate `data/*/story.db`; directory name is immutable `project_id`.
- Project IDs match `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$`, length 1–64.
- `project.json` persists only `project_id`, `status`, `created_at`, `updated_at`.
- Status values are exactly `active` and `archived`.
- Archived projects are hidden from default lists but remain fully readable/writable by explicit `project_id`.
- No project-delete endpoint.
- Missing `project.json` does not hide an existing `story.db`: synthesize active metadata in memory with `metadata_state="missing"`; listing must not write metadata.
- Malformed/mismatched `project.json` does not hide an existing `story.db`: synthesize active metadata in memory with `metadata_state="invalid"`; listing must not rewrite metadata.
- Project creation stages under `data/.staging/` and finalizes by same-filesystem rename only after migrations, work initialization, integrity verification, and metadata write succeed.
- Default API bind is `0.0.0.0:8765`; port is configurable. Bind failure must fail explicitly, never silently select another port.
- Initial deployment is trusted-LAN only: no authentication/user system and no direct-public-Internet scope.
- Development CORS may allow one configured Vite origin; no wildcard production CORS.
- FastAPI static WEBUI serving belongs to Phase D; Phase B is API-only.
- Issue #5 and Phase 4 continuity/inconsistency work remain out of scope.

---

## File Structure After Phase B

```text
API/
├─ pyproject.toml
├─ src/novel_api/
│  ├─ __init__.py
│  ├─ app.py
│  ├─ cli.py
│  ├─ config.py
│  ├─ dependencies.py
│  ├─ errors.py
│  ├─ project_registry.py
│  ├─ serialization.py
│  ├─ service_container.py
│  ├─ routes/
│  │  ├─ __init__.py
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
│     ├─ __init__.py
│     ├─ common.py
│     ├─ projects.py
│     ├─ work.py
│     ├─ world.py
│     ├─ timeline.py
│     ├─ characters.py
│     ├─ canon.py
│     ├─ narrative.py
│     ├─ information.py
│     ├─ authoring.py
│     └─ views.py
└─ tests/
   ├─ conftest.py
   ├─ test_health.py
   ├─ test_cli.py
   ├─ test_projects.py
   ├─ test_project_atomicity.py
   ├─ test_request_connections.py
   ├─ test_errors.py
   ├─ test_phase1_api.py
   ├─ test_phase2_api.py
   ├─ test_phase3_api.py
   ├─ test_views.py
   └─ test_multi_project_e2e.py

CORE/src/novel_core/database.py
CORE/src/novel_core/errors.py
CORE/tests/test_database_lifecycle.py
.github/workflows/mcp-ci.yml
MCP/scripts/check_source_size.py
README.md
```

---

### Task 1: Create API package, settings, app factory, health endpoint, and CLI

**Files:**
- Create all Task 1 files shown above: `API/pyproject.toml`, `__init__.py`, `config.py`, `app.py`, `cli.py`, `routes/__init__.py`, `routes/health.py`, `tests/test_health.py`, `tests/test_cli.py`.

**Interfaces:**
- `ApiSettings(data_root: Path, host: str = "0.0.0.0", port: int = 8765, dev_cors_origin: str | None = None)`
- `create_app(settings: ApiSettings) -> FastAPI`
- `main(argv: list[str] | None = None) -> None`
- `GET /api/v1/health`

- [ ] **Step 1: Create `API/pyproject.toml`**

Use:

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
source = ["src/novel_api"]

[tool.coverage.report]
fail_under = 80
show_missing = true

[tool.ruff]
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: Write failing health/CLI tests**

Health test:

```python
def test_health_is_api_only_and_does_not_require_project(tmp_path: Path) -> None:
    app = create_app(ApiSettings(data_root=tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "v1"}
```

CLI tests assert default host `0.0.0.0`, port `8765`, explicit `--host`, `--port`, `--data-root`, and environment variables `NOVEL_DATA_ROOT`, `NOVEL_API_HOST`, `NOVEL_API_PORT`, `NOVEL_DEV_CORS_ORIGIN`.

Run and confirm RED before implementation:

```bash
cd API
uv sync --all-groups
uv run pytest tests/test_health.py tests/test_cli.py -q
```

- [ ] **Step 3: Implement `ApiSettings` and deterministic data-root resolution**

Resolution order:

1. explicit CLI value;
2. environment value;
3. source-checkout root only when `Path(__file__).resolve().parents[3]` contains both `CORE/` and `MCP/`, then `<root>/data`;
4. otherwise `Path.cwd()/data`.

- [ ] **Step 4: Implement app factory, `/api/v1/health`, and CLI**

Health must not discover/open DBs. CLI creates the app object and calls `uvicorn.run(app, host=..., port=...)`; do not probe for a free alternate port.

- [ ] **Step 5: Verify and commit**

```bash
cd API
uv run pytest tests/test_health.py tests/test_cli.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Commit: `feat: add FastAPI application foundation`.

---

### Task 2: Add CORE integrity verification and filesystem project registry

**Files:**
- Modify `CORE/src/novel_core/database.py`, `CORE/src/novel_core/errors.py`, `CORE/tests/test_database_lifecycle.py`.
- Create `API/src/novel_api/project_registry.py`, `schemas/projects.py`, `routes/projects.py`, `tests/conftest.py`, `tests/test_projects.py`, `tests/test_project_atomicity.py`.

**Interfaces:**
- `DatabaseIntegrityError`
- `assert_database_integrity(connection: sqlite3.Connection) -> None`
- `ProjectRegistry(data_root: Path)`
- `ProjectNotFoundError`, `ProjectConflictError`
- `ProjectRegistry.list(include_archived: bool = False)`
- `ProjectRegistry.get(project_id: str)`
- `ProjectRegistry.create(working_title: str, project_id: str | None = None)`
- `ProjectRegistry.set_status(project_id: str, status: Literal["active", "archived"])`

- [ ] **Step 1: Write failing CORE integrity tests, then implement CORE helper**

`assert_database_integrity` executes `PRAGMA integrity_check`; only one-row `ok` succeeds. All other/no-result states raise `DatabaseIntegrityError`. Keep existing DB/migration behavior unchanged.

Run:

```bash
cd CORE
uv run pytest -W error
```

- [ ] **Step 2: Define project metadata models exactly**

Persisted JSON:

```json
{
  "project_id": "winter-tokyo",
  "status": "active",
  "created_at": "2026-08-28T00:00:00Z",
  "updated_at": "2026-08-28T00:00:00Z"
}
```

Derived API summary fields:

```text
project_id: str
status: active | archived
metadata_state: ok | missing | invalid
working_title: str | null
created_at: str | null
updated_at: str | null
health: ok | degraded
```

`health` and `metadata_state` are never persisted.

- [ ] **Step 3: Write discovery tests before implementation**

Cover: missing metadata, archived filtering, include-archived, malformed/mismatched metadata still visible, no-story.db ignored, `.staging/<token>/story.db` not discovered as immediate project, unknown project 404 path, invalid/traversal/Unicode IDs rejected.

- [ ] **Step 4: Implement immediate-child discovery and read-only summary hydration**

Missing/invalid metadata defaults to active in memory. Project-list hydration opens each story DB through CORE only long enough to call `WorkService.get`, closes it immediately, and reports `health="degraded"`, `working_title=null` if that DB cannot be read. Listing never edits project metadata or story data intentionally.

- [ ] **Step 5: Write atomic-create failure/success tests**

Cover explicit ID, auto ID `project-YYYYMMDD-HHMMSS`, collision suffix `-2/-3`, no title translation, duplicate conflict, failure cleanup, exact migrations 001–004, one work row, valid project.json, no path outside temp data root.

- [ ] **Step 6: Implement staged creation with exclusive per-project lock**

Flow:

```text
validate/generate ID
-> acquire data/.locks/<project_id>.lock using O_CREAT|O_EXCL
-> create data/.staging/<uuid>/
-> initialize_work(staging/story.db, working_title=...)
-> open staging DB through CORE
-> assert_database_integrity
-> close DB
-> write staging/project.json
-> verify final path absent
-> Path.rename(staging_dir, data/<project_id>) on same filesystem
-> remove lock in finally
```

Never overwrite an existing final directory.

- [ ] **Step 7: Implement archive/restore with atomic metadata replace**

`PATCH /api/v1/projects/{project_id}` accepts only `{"status":"active"}` or `{"status":"archived"}`. Write a same-directory temporary metadata file then `os.replace`. Explicit update repairs missing/invalid metadata; when no valid prior `created_at` exists, set it to the update time.

- [ ] **Step 8: Implement project routes**

```text
GET   /api/v1/projects?include_archived=false
POST  /api/v1/projects
GET   /api/v1/projects/{project_id}
PATCH /api/v1/projects/{project_id}
```

POST body: required non-empty `working_title`, optional `project_id`.

- [ ] **Step 9: Verify and commit**

Run full CORE plus focused API project tests, Ruff/format/mypy. Commit: `feat: add atomic multi-project registry`.

---

### Task 3: Add thread-affine per-request CORE service execution

**Files:**
- Create `API/src/novel_api/service_container.py`, `API/src/novel_api/dependencies.py`, `API/tests/test_request_connections.py`.

**Interfaces:**
- `ServiceContainer` with all current 16 CORE services.
- `ProjectTarget(project_id, descriptor)`; contains no open SQLite connection.
- `resolve_project_target(...) -> ProjectTarget`; filesystem/registry lookup only.
- `open_project_services(target: ProjectTarget) -> ContextManager[ServiceContainer]`.

- [ ] **Step 1: Implement typed service container**

Compose exactly:

```text
WorkService, WorldFactService, TimelineService, CharacterService,
RelationshipService, CanonService, SearchService, NarrativeService,
CharacterStateService, InformationService, DisclosureService,
KnowledgeService, EpisodeReferenceService, DraftService,
OutlineService, ContextService
```

- [ ] **Step 2: Write connection/thread-lifecycle tests before implementation**

Prove that:

1. `resolve_project_target` does not open SQLite;
2. each project-scoped HTTP request opens exactly one connection;
3. all CORE services in that request share that same connection;
4. next request gets a different connection;
5. success and exception paths close it;
6. archived project executes normally;
7. unknown project fails before DB open.

- [ ] **Step 3: Implement local context-manager execution**

`open_project_services` does:

```text
open_database(DatabaseConfig(target.story_db, default_migration_dir()))
-> build ServiceContainer(connection)
-> yield services
-> connection.close() in finally
```

All project DB route functions introduced in Tasks 5–8 are synchronous `def` and enter this context manager inside the route function itself. Do not yield an open connection/service container from a FastAPI dependency.

- [ ] **Step 4: Add HTTP search -> write regression**

On a temp project perform one search request followed by a write request; assert write succeeds and no transaction state leaks.

- [ ] **Step 5: Verify and commit**

Run focused tests/Ruff/format/mypy. Commit: `feat: add request scoped project services`.

---

### Task 4: Implement common success/error contract and conflict snapshots

**Files:**
- Create `API/src/novel_api/schemas/common.py`, `serialization.py`, `errors.py`, `tests/test_errors.py`; modify `app.py`.

**Interfaces:**

```python
T = TypeVar("T")

class ProjectEnvelope(BaseModel, Generic[T]):
    project_id: str
    data: T
```

Error contract:

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "The resource was modified by another client.",
    "project_id": "2126",
    "details": {}
  }
}
```

- [ ] **Step 1: Write exact mapping tests**

```text
RequestValidationError / CORE ValidationError / ValueError -> 400 VALIDATION_ERROR
ProjectNotFoundError                                  -> 404 PROJECT_NOT_FOUND
CORE *NotFoundError / WorkScopeError                  -> 404 NOT_FOUND
VersionConflictError                                  -> 409 VERSION_CONFLICT
OrderConflictError                                    -> 409 ORDER_CONFLICT
RelationshipIntegrityError / sqlite IntegrityError    -> 409 DEPENDENCY_CONFLICT
CanonPolicyError                                      -> 409 DEPENDENCY_CONFLICT
locked sqlite OperationalError                        -> 503 DATABASE_BUSY
unexpected exception                                  -> 500 INTERNAL_ERROR
```

For every normalized domain-specific error, include `details.domain_code` with the CORE class/code name. Never expose raw SQLite messages/tracebacks.

- [ ] **Step 2: Implement one exception-handler installation function**

Install handlers from `create_app` for request validation, project exceptions, CORE errors, SQLite errors, fallback exceptions. API paths return JSON only.

- [ ] **Step 3: Implement reusable conflict helper**

Routes that know the entity and can re-read after the CORE service rollback attach:

```json
{
  "entity_type": "episode",
  "entity_id": 14,
  "expected_version": 4,
  "current_version": 5,
  "current_resource": {}
}
```

Do not parse versions from exception strings. Global fallback VERSION_CONFLICT may omit snapshot details when no safe read function exists.

- [ ] **Step 4: Verify and commit**

Run `tests/test_errors.py`, Ruff/format/mypy. Commit: `feat: add shared API error contract`.

---

### Task 5: Expose all 23 Phase 1 operations over HTTP

**Files:**
- Create `schemas/work.py`, `world.py`, `timeline.py`, `characters.py`, `canon.py`; create matching route files; create `tests/test_phase1_api.py`; modify `app.py`.

**Route inventory:**

```text
GET   /api/v1/projects/{project_id}/work
PATCH /api/v1/projects/{project_id}/work
POST  /api/v1/projects/{project_id}/world-facts
GET   /api/v1/projects/{project_id}/world-facts/search?query=&limit=20
GET   /api/v1/projects/{project_id}/world-facts/{fact_id}
PATCH /api/v1/projects/{project_id}/world-facts/{fact_id}
POST  /api/v1/projects/{project_id}/timeline/events
GET   /api/v1/projects/{project_id}/timeline/events/search?query=&limit=20
GET   /api/v1/projects/{project_id}/timeline/events/{event_id}
PATCH /api/v1/projects/{project_id}/timeline/events/{event_id}
GET   /api/v1/projects/{project_id}/timeline/range?start=&end=&limit=20
POST  /api/v1/projects/{project_id}/timeline/events/{event_id}/move
POST  /api/v1/projects/{project_id}/timeline/relations
POST  /api/v1/projects/{project_id}/characters
GET   /api/v1/projects/{project_id}/characters/search?query=&limit=20
GET   /api/v1/projects/{project_id}/characters/{character_id}
PATCH /api/v1/projects/{project_id}/characters/{character_id}
POST  /api/v1/projects/{project_id}/relationships
PATCH /api/v1/projects/{project_id}/relationships/{relationship_id}
GET   /api/v1/projects/{project_id}/relationships?character_id=&limit=20
POST  /api/v1/projects/{project_id}/canon/status
GET   /api/v1/projects/{project_id}/canon/decisions/search?query=&limit=20
GET   /api/v1/projects/{project_id}/canon/decisions/{decision_id}
```

**Static-route ordering rule:** register `/search` routes before dynamic `/{id}` routes in the same router so literal `search` is never captured as an integer ID path.

**Request fields:**

```text
WorkUpdate: working_title, expected_version, genre?, premise?, themes_json?, description?, production_status?
WorldFactCreate: statement, valid_from?, valid_to?, topic_key?, category="general", title?, details_json={}, importance=0
WorldFactUpdate: statement, expected_version, reason?, topic_key?, category?, title?, details_json?, valid_from?, valid_to?, importance?
TimelineParticipant: character_id, role
TimelineEventCreate: title, event_date?, participants?, event_key?, time_start?, time_end?, date_precision?, date_display?, description="", category="general", location_world_fact_id?, cause_summary="", consequence_summary="", importance=0
TimelineEventUpdate: expected_version, title?, new_date?, participants?, reason?, time_start?, time_end?, date_precision?, date_display?, description?, category?, location_world_fact_id?, cause_summary?, consequence_summary?, importance?
TimelineMove: expected_version, new_date, reason?
TimelineRelationCreate: source_id, target_id, relation_type
CharacterCreate: display_name, character_key?, entity_type="human", description="", birth_date?, death_date?, physical_description="", occupation="", core_beliefs="", goals="", fears="", personality="", speech_style="", ai_attitude="", genetic_modification_attitude="", private_notes="", profile_json={}
CharacterUpdate: expected_version, display_name?, description?, reason?, character_key?, entity_type?, birth_date?, death_date?, physical_description?, occupation?, core_beliefs?, goals?, fears?, personality?, speech_style?, ai_attitude?, genetic_modification_attitude?, private_notes?, profile_json?
RelationshipCreate: source_character_id, target_character_id, relationship_type, description="", valid_from_episode_id?, valid_to_episode_id?
RelationshipUpdate: expected_version, relationship_type, description?, reason?, valid_from_episode_id?, valid_to_episode_id?, clear_valid_from=false, clear_valid_to=false
CanonStatusSet: entity_type, entity_id, target_status, expected_version, reason?
```

- [ ] **Step 1: Write table-driven failing tests covering all 23 operations**

Include Japanese search, timeline range/move/relation, relationship validation, canon policy, stale update 409/current snapshot, and cross-project isolation.

- [ ] **Step 2: Implement thin synchronous route handlers**

Each route resolves `ProjectTarget`, enters `open_project_services(target)` exactly once, calls CORE service(s), wraps result. JSON-like request values are converted at transport boundary to compact JSON strings only where current CORE expects strings.

- [ ] **Step 3: Verify and commit**

Run Phase 1 tests/Ruff/format/mypy. Commit: `feat: expose Phase 1 HTTP API`.

---

### Task 6: Expose all 27 Phase 2 operations over HTTP

**Files:**
- Create `schemas/narrative.py`, `schemas/information.py`, `routes/narrative.py`, `routes/information.py`, `tests/test_phase2_api.py`; modify `app.py`.

**Route inventory:**

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
POST  /api/v1/projects/{project_id}/information
GET   /api/v1/projects/{project_id}/information/search?query=&limit=20
GET   /api/v1/projects/{project_id}/information/{information_item_id}
PATCH /api/v1/projects/{project_id}/information/{information_item_id}
PUT /api/v1/projects/{project_id}/information/{information_item_id}/reader-disclosure
PUT /api/v1/projects/{project_id}/characters/{character_id}/knowledge/{information_item_id}
GET /api/v1/projects/{project_id}/characters/{character_id}/knowledge?episode_id=
```

Register information `/search` before dynamic `/{information_item_id}`.

**Request fields:**

```text
ChapterCreate: title, summary="", purpose="", production_status="planned", canon_status="draft"
ChapterUpdate: expected_version, title?, summary?, purpose?, production_status?, canon_status?, reason?
Reorder: target_position, expected_version
EpisodeCreate: title, summary="", purpose="", foreshadowing_notes?, production_status="planned", canon_status="draft"
EpisodeUpdate: expected_version, title?, summary?, purpose?, foreshadowing_notes?, production_status?, canon_status?, reason?
SceneCreate: title, summary="", purpose="", production_status="planned", canon_status="draft"
SceneUpdate: expected_version, title?, summary?, purpose?, production_status?, canon_status?, reason?
EpisodeReferenceAdd: reference_type, target_id, role="participant"
CharacterStateSet: physical_state?, emotional_state?, beliefs_json?, location_world_fact_id?, state_json?, expected_version?
InformationCreate: statement, truth_status="uncertain", authoring_guard="", notes_json?, canon_status="draft", importance=0
InformationUpdate: expected_version, statement?, truth_status?, authoring_guard?, notes_json?, importance?, canon_status?, reason?
ReaderDisclosureSet: episode_id, expected_version?
CharacterKnowledgeSet: episode_id, knowledge_state, note="", expected_version?
```

- [ ] **Step 1: Write failing tests covering all 27 operations**

Include hierarchy reorder, reference add/list/remove, state history/effective lookup, information search, disclosure, knowledge, stale versions, cross-project IDs, deprecated/canon guards.

- [ ] **Step 2: Implement thin synchronous handlers**

Narrative update/reorder conflict handlers re-read current entity after CORE rollback and attach latest snapshot. The reference DELETE implements only existing `episode_reference_remove`; do not add chapter/episode/scene deletion or Issue #5 semantics.

- [ ] **Step 3: Verify and commit**

Run Phase 2 tests/Ruff/format/mypy. Commit: `feat: expose Phase 2 HTTP API`.

---

### Task 7: Expose all 5 Phase 3 authoring operations over HTTP

**Files:**
- Create `schemas/authoring.py`, `routes/authoring.py`, `tests/test_phase3_api.py`; modify `app.py`.

**Routes:**

```text
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/outline
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/context
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/draft?revision=
POST /api/v1/projects/{project_id}/episodes/{episode_id}/drafts
GET  /api/v1/projects/{project_id}/episodes/{episode_id}/drafts?limit=20
```

Draft-save body:

```text
body: non-empty string
expected_parent_draft_id?: positive int
source_agent?: 1..120 chars
change_summary: max 1000 chars, default ""
```

- [ ] **Step 1: Write failing tests**

Cover outline/context, future/disclosure guards, absent draft returns `data:null`, first/second saves, history, stale parent returns 409 + latest draft snapshot, append-only behavior, cross-project failure.

- [ ] **Step 2: Implement synchronous handlers**

Do not add structured JSON draft support or migration 005.

- [ ] **Step 3: Verify and commit**

Run Phase 3 tests/Ruff/format/mypy. Commit: `feat: expose Phase 3 authoring API`.

---

### Task 8: Add initial derived WEBUI read views

**Files:**
- Create `schemas/views.py`, `routes/views.py`, `tests/test_views.py`; modify `app.py`.

**Routes:**

```text
GET /api/v1/projects/{project_id}/views/outline
GET /api/v1/projects/{project_id}/views/dashboard
GET /api/v1/projects/{project_id}/views/episodes/{episode_id}
```

- [ ] **Step 1: Write failing deterministic view tests**

Use a temp project with multiple chapters/episodes/scenes. Reads must not change versions or write DB state.

- [ ] **Step 2: Implement `/views/outline`**

Return hierarchy ordered by existing CORE list semantics:

```json
{"chapters":[{"chapter":{},"episodes":[{"episode":{},"scenes":[]}]}]}
```

Use `NarrativeService.list_chapters/list_episodes/list_scenes`; no API SQL.

- [ ] **Step 3: Implement `/views/dashboard`**

Return `work`, `chapter_count`, `episode_count`, `scene_count`, with counts derived from the same hierarchy read.

- [ ] **Step 4: Implement `/views/episodes/{episode_id}`**

Return `episode`, `scenes`, `episode_references`, `outline`, `context`, `latest_draft`, `recent_draft_history` (20). Missing draft is null. Context guards remain identical to fine-grained context endpoint.

- [ ] **Step 5: Verify and commit**

Run view tests/Ruff/format/mypy. Commit: `feat: add derived authoring API views`.

---

### Task 9: Add multi-project/concurrency E2E and LAN runtime guardrails

**Files:**
- Create `tests/test_multi_project_e2e.py`; modify `app.py`, `README.md`.

- [ ] **Step 1: Multi-project isolation E2E**

Create `alpha`/`beta`, create colliding numeric IDs in both, verify explicit project routing never leaks content and every project response reports the addressed ID.

- [ ] **Step 2: Optimistic concurrency E2E**

Read version N, client A writes expected N -> N+1, client B writes expected N -> 409 with expected/current/latest snapshot, final GET remains A's value.

- [ ] **Step 3: Archive semantics E2E**

Archive -> hidden by default list -> shown with include-archived -> explicit read/write succeeds -> restore -> default list includes again.

- [ ] **Step 4: Development CORS**

Install CORS middleware only when `dev_cors_origin` is non-null and allow exactly that origin. No wildcard origin.

- [ ] **Step 5: README runtime docs**

State: default `0.0.0.0:8765`, trusted LAN/no auth, MCP still CORE-direct in Phase B, Phase C future API URL `http://127.0.0.1:8765/api/v1`, WEBUI static serving deferred to Phase D. Development examples must use a temp/sandbox data root, not stable `data/2126`.

- [ ] **Step 6: Verify and commit**

Run E2E; commit `test: verify multi-project API isolation`.

---

### Task 10: Integrate API CI and perform complete Phase B verification

**Files:**
- Modify `.github/workflows/mcp-ci.yml`, `MCP/scripts/check_source_size.py`, `docs/superpowers/plans/2026-08-28-novelproduction-delivery-plan-index.md`.

- [ ] **Step 1: Extend existing source-size script without relaxing policy**

Inspect exactly:

```text
CORE/src, CORE/tests, API/src, API/tests, MCP/src, MCP/tests
```

Split oversized files; do not raise thresholds.

- [ ] **Step 2: Add `api` CI job**

Python 3.13, working directory `API`:

```text
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_api --cov-report=term-missing
```

Keep existing CORE wheel smoke, MCP checks, tool count 55, and exact migration/invariant job.

- [ ] **Step 3: Add dependency-boundary checks**

Fail if API imports `novel_mcp`/`mcp`, CORE imports API/FastAPI/MCP, API route modules contain direct story SQL execution, migration 005 appears, or MCP tool inventory differs from 55. `sqlite3` is permitted only in API error/type plumbing, not as story persistence logic.

- [ ] **Step 4: Run full clean-worktree verification**

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

Also execute the Phase A migration invariant logic and verify exact 001–004 canonical blobs, no 005, no `MCP/migrations`, MCP tool count 55.

- [ ] **Step 5: Verify scope/safety**

Report exactly:

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

- [ ] **Step 6: Update delivery index**

Phase B plan path becomes `docs/superpowers/plans/2026-08-28-novelproduction-phase-b-api-foundation.md`. Leave Phase C plan unwritten until Phase B API contract is merged/reviewed.

- [ ] **Step 7: Push and open Draft PR**

Title: `[Issue #8] Add shared FastAPI v1 backend and project registry`.

PR body includes `Refs #8`, parent #6, endpoint coverage (23+27+5 = 55 existing operations), project registry semantics, one-request/one-connection evidence, error/conflict evidence, aggregate views, test/coverage/CI results, and explicit no-production-DB/Tunnel/Connector/no-Phase-C statements. Do not merge.

---

## Endpoint Coverage Gate

Before accepting Phase B, reviewer must map all existing operations:

```text
Phase 1: 23
Phase 2: 27
Phase 3: 5
Total existing project-data operations exposed over HTTP: 55
```

Project-management and derived-view endpoints are additional and are not counted in the 55.

## Phase B Exit State

```text
Future WEBUI/browser ─HTTP─> API/FastAPI ─> CORE ─> project SQLite DB

MCP ───────────────────────> CORE ─> configured SQLite DB
      temporary Phase B compatibility path only
```

Phase C removes the direct MCP→CORE runtime path and adds explicit `project_id` to MCP tools. Phase B must not pre-implement that cutover.
