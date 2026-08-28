# NovelProduction Shared CORE/API and WEBUI Architecture Design

Date: 2026-08-28
Status: Proposed — awaiting written-spec review
Repository: `weito-crowry/NovelProduction`

## 1. Purpose

NovelProduction currently provides the novel-production domain model and authoring workflow through the MCP component. The next stage adds a first-class browser UI while preserving ChatGPT/MCP access and avoiding duplicate business logic.

This design introduces four explicit components:

- `CORE/`: shared domain, validation, transaction, repository, migration, and document logic.
- `API/`: the common FastAPI HTTP boundary used by both WEBUI and MCP.
- `MCP/`: a stateless MCP-to-HTTP adapter for ChatGPT and other MCP clients.
- `WEBUI/`: a React + Vite browser UI for human editing and inspection.

The API becomes the only supported runtime data-access entry point. MCP and WEBUI are independent clients of the same API and do not share hidden selection state.

## 2. Goals

1. Provide a LAN-accessible browser UI for all data currently exposed through the Phase 1–3 MCP feature set.
2. Support multiple works under `data/<project_id>/story.db` and allow WEBUI users to switch between them.
3. Allow new projects to be created from WEBUI.
4. Keep MCP access safe and explicit by requiring `project_id` on every project-scoped MCP tool call.
5. Extract reusable domain logic from `novel_mcp` into a component that is independent of MCP and WEBUI.
6. Make FastAPI the single supported runtime path to SQLite.
7. Preserve optimistic version checking and fail closed on conflicts.
8. Add structured JSON draft documents that can carry metadata on narrative blocks while retaining rendered plain text for LLM, search, and export use.
9. Keep the production runtime simple: one FastAPI process serves both the API and the built React application, while the source tree remains logically separated.
10. Keep the system evolvable: API versioning, document schema versioning, and adapter boundaries must permit future changes without rewriting stored history.

## 3. Non-goals

This design does not include:

- direct Internet exposure;
- authentication or user-account management;
- project deletion;
- automatic migration of the existing story content into the new architecture;
- a general physical-delete feature for all canon entities;
- Phase 4 continuity/inconsistency detection;
- automatic prose generation inside CORE or API;
- a requirement to keep the current real `story.db` byte-for-byte/data compatible through the architectural cutover.

Issue #5 (`Support shrinking narrative outlines without stale active episodes`) remains a separate structural-editing concern. The new UI/API architecture should make its eventual behavior visible, but this design does not redefine that issue.

## 4. Repository layout

Target layout:

```text
NovelProduction/
├─ CORE/
│  ├─ migrations/
│  │  ├─ 001_initial.sql
│  │  ├─ 002_search.sql
│  │  ├─ 003_narrative.sql
│  │  ├─ 004_drafts.sql
│  │  └─ 005_structured_drafts.sql
│  └─ src/novel_core/
│     ├─ database.py
│     ├─ errors.py
│     ├─ models/
│     ├─ repositories/
│     ├─ services/
│     └─ document/
│        ├─ schema.py
│        ├─ renderer.py
│        └─ migrations.py
│
├─ API/
│  └─ src/novel_api/
│     ├─ app.py
│     ├─ routes/
│     ├─ schemas/
│     ├─ errors.py
│     └─ project_registry.py
│
├─ MCP/
│  └─ src/novel_mcp/
│     ├─ mcp_server.py
│     ├─ api_client.py
│     └─ tool adapters
│
├─ WEBUI/
│  └─ frontend/
│     ├─ src/
│     └─ dist/              # generated build output, not source of truth
│
├─ data/
│  ├─ 2126/
│  │  ├─ story.db
│  │  └─ project.json
│  └─ <project_id>/
│     ├─ story.db
│     └─ project.json
│
└─ docs/
```

The exact internal file split may be refined during implementation, but dependency direction must not change.

## 5. Dependency direction

The dependency graph is:

```text
WEBUI (React) ──HTTP──┐
                      ├──> API (FastAPI) ──> CORE ──> SQLite
ChatGPT ──> MCP ─HTTP─┘
```

Rules:

- WEBUI must not import CORE or access SQLite directly.
- MCP must not import CORE for runtime data access after the HTTP cutover.
- MCP must not fall back to direct SQLite access when API is unavailable.
- API may depend on CORE.
- CORE must not depend on API, MCP, React, FastAPI, or TipTap.
- SQLite access is owned by CORE and reached through API at runtime.

## 6. Project model and discovery

### 6.1 Discovery

The API discovers projects from:

```text
data/*/story.db
```

Each directory name is the immutable `project_id`.

Examples:

```text
data/2126/story.db          -> project_id = "2126"
data/winter-tokyo/story.db  -> project_id = "winter-tokyo"
```

Titles, genre, premise, description, themes, and production state remain canonical inside `story.db`.

### 6.2 `project.json`

`project.json` contains only outer project-management metadata that should be available without treating story metadata as duplicated truth.

Initial form:

```json
{
  "project_id": "2126",
  "status": "active",
  "created_at": "2026-08-28T00:00:00Z",
  "updated_at": "2026-08-28T00:00:00Z"
}
```

Allowed status values initially:

- `active`
- `archived`

`archived` is an organizational state only. It does not make the project read-only.

Normal project lists omit archived projects. Explicit project access continues to allow read and write operations.

### 6.3 Project creation

WEBUI and MCP/API support project creation.

Input contains:

- required `working_title`;
- optional `project_id`.

If supplied, `project_id` must use a conservative URL/filesystem-safe form based on lowercase ASCII letters, digits, and hyphens. The implementation should enforce a bounded length and reject path separators, dot traversal, whitespace, and Unicode lookalikes.

If `project_id` is omitted, generate an opaque stable ID such as:

```text
project-20260828-053812
```

A collision suffix may be added if necessary. The system must not use LLM translation or title-to-English inference to generate IDs.

Creation flow:

```text
validate request
  -> choose/validate project_id
  -> verify no collision
  -> create in a temporary location
  -> create story.db
  -> apply CORE migrations
  -> initialize the work row
  -> verify database integrity
  -> write project.json
  -> atomically finalize data/<project_id>/
```

If any step fails, the incomplete project must not appear in normal discovery.

`project_id` is immutable after successful creation.

### 6.4 Project deletion and archive

Project deletion is not exposed in the initial API or WEBUI.

Archiving is supported:

```text
active -> archived
archived -> active
```

Archived projects:

- are hidden from default project lists;
- appear when `include_archived=true` is requested;
- remain fully readable and writable when addressed explicitly by `project_id`.

## 7. API architecture

### 7.1 Versioning

All public API routes use the prefix:

```text
/api/v1
```

Examples:

```text
GET  /api/v1/health
GET  /api/v1/projects
GET  /api/v1/projects/2126/work
GET  /api/v1/projects/2126/chapters
GET  /api/v1/projects/2126/views/outline
POST /api/v1/projects/2126/episodes
```

Breaking HTTP-contract changes require a new API version rather than silently changing v1 semantics.

### 7.2 Fine-grained resource/command API

The base API should map cleanly to CORE operations and existing MCP semantics.

Representative routes:

```text
GET    /api/v1/projects/{project_id}/work
PATCH  /api/v1/projects/{project_id}/work

GET    /api/v1/projects/{project_id}/chapters
POST   /api/v1/projects/{project_id}/chapters
PATCH  /api/v1/projects/{project_id}/chapters/{chapter_id}

GET    /api/v1/projects/{project_id}/chapters/{chapter_id}/episodes
POST   /api/v1/projects/{project_id}/chapters/{chapter_id}/episodes
GET    /api/v1/projects/{project_id}/episodes/{episode_id}
PATCH  /api/v1/projects/{project_id}/episodes/{episode_id}

GET    /api/v1/projects/{project_id}/episodes/{episode_id}/context
GET    /api/v1/projects/{project_id}/episodes/{episode_id}/drafts
POST   /api/v1/projects/{project_id}/episodes/{episode_id}/drafts
```

The final endpoint inventory must cover the existing Phase 1–3 capabilities.

All writes must call CORE services. API handlers must not duplicate domain validation or issue direct story SQL.

### 7.3 Aggregated WEBUI query/view API

WEBUI may use read-only aggregated endpoints to reduce request fan-out.

Examples:

```text
GET /api/v1/projects/{project_id}/views/dashboard
GET /api/v1/projects/{project_id}/views/outline
GET /api/v1/projects/{project_id}/views/characters/{character_id}
GET /api/v1/projects/{project_id}/views/episodes/{episode_id}
GET /api/v1/projects/{project_id}/views/timeline
GET /api/v1/projects/{project_id}/views/canon
```

These are derived views, not alternate storage or alternate truth.

Write semantics remain in the fine-grained command/resource API and CORE services.

### 7.4 Project identity in responses

Project-scoped responses should include `project_id` so logs, MCP results, and UI diagnostics always identify the work that was read or modified.

## 8. Error contract

API failures use a common structured shape:

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "The resource was modified by another client.",
    "project_id": "2126",
    "details": {
      "entity_type": "episode",
      "entity_id": 14,
      "expected_version": 4,
      "current_version": 5
    }
  }
}
```

Initial HTTP mapping:

| HTTP | Code | Purpose |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | Invalid request/domain input |
| 404 | `PROJECT_NOT_FOUND` / `NOT_FOUND` | Project or entity missing |
| 409 | `VERSION_CONFLICT` | Optimistic concurrency conflict |
| 409 | `ORDER_CONFLICT` | Reorder conflict |
| 409 | `DEPENDENCY_CONFLICT` | Protected dependent data prevents an operation |
| 422 | `DOCUMENT_SCHEMA_ERROR` | Structured document invalid |
| 503 | `DATABASE_BUSY` | SQLite remains locked after the configured wait |
| 503 | `BACKEND_UNAVAILABLE` | Used by MCP when the HTTP backend cannot be reached |
| 500 | `INTERNAL_ERROR` | Unexpected server failure |

For `VERSION_CONFLICT`, the API should include the latest resource snapshot when it can do so safely. WEBUI uses this to show a side-by-side comparison.

CORE exceptions are mapped once in the API layer. WEBUI and MCP must not invent incompatible error taxonomies.

## 9. SQLite connection and concurrency model

### 9.1 One request, one connection

Each API request that needs story data opens a project-specific SQLite connection and closes it at request completion.

Required connection settings preserve current safety behavior:

- `PRAGMA foreign_keys = ON`
- WAL mode
- `busy_timeout = 5000` (or equivalent 5-second policy)

The connection must not be shared across unrelated HTTP requests.

This prevents transaction/search state from leaking between requests and provides a simpler concurrency boundary for multiple browsers plus MCP traffic.

### 9.2 Transactions

Rules:

- keep write transactions short;
- perform no external HTTP calls while a database write transaction is open;
- use explicit commit/rollback behavior in CORE;
- do not use silent last-write-wins updates;
- preserve optimistic `expected_version` checking.

Example:

```text
WEBUI reads episode version 7
MCP updates it -> version 8
WEBUI saves with expected_version 7
-> HTTP 409 VERSION_CONFLICT
```

The existing search -> write transaction regression must remain covered after extraction.

## 10. CORE ownership and migrations

### 10.1 CORE responsibilities

CORE owns:

- SQLite lifecycle;
- domain services;
- repositories;
- validation;
- canon transitions;
- optimistic version checks;
- ordering/reordering rules;
- project DB initialization;
- database migrations;
- structured document validation/rendering/version adapters.

### 10.2 Existing migrations

Move migrations `001` through `004` under `CORE/migrations/` without changing their SQL content.

The architectural cutover does not promise to preserve current real story data. The existing `data/2126/story.db` may be backed up and then deleted/recreated once the new CORE/API path is ready.

The implementation must not destructively touch the real DB until the cutover step is explicitly executed.

Keep the migration lifecycle's EOL-independent checksum behavior when it moves into CORE.

New schema changes begin with migration `005`.

## 11. Structured draft document design

### 11.1 Storage model

Existing draft behavior is append-only and remains append-only.

A new migration extends drafts with structured-document fields conceptually equivalent to:

```text
document_json
document_schema_version
document_hash
```

Existing `body` remains a rendered plain-text representation.

For structured drafts:

```text
document_json = canonical structured draft content
      -> CORE renderer
body = derived plain-text content
```

`body` and `document_json` must not be independently editable through the public API when structured content is present.

### 11.2 Document schema

Initial document envelope:

```json
{
  "schema_version": 1,
  "type": "novel_document",
  "content": [
    {
      "id": "blk_001",
      "type": "dialogue",
      "text": "また雪か。",
      "attrs": {
        "speaker_character_id": 3,
        "scene_id": 4
      },
      "annotations": {}
    }
  ]
}
```

The stable block core is:

- `id`
- `type`
- `text`
- `attrs`
- `annotations`

Initial block types:

- `narration`
- `dialogue`
- `thought`
- `description`
- `quote`
- `separator`
- `heading`
- `note`

`attrs` represents semantic attributes needed to interpret the block, for example:

- `speaker_character_id`
- `addressee_character_ids`
- `scene_id`
- language or other later structural attributes

`annotations` is intentionally extensible and may later include:

- emotion
- intent
- tags
- foreshadowing/thread references
- AI analysis output
- continuity annotations

New metadata keys must be addable without a database schema change.

### 11.3 Schema evolution

The top-level `schema_version` is mandatory for structured drafts.

Past draft revisions are never rewritten merely to upgrade the document schema. Compatibility is handled by document readers/adapters, or by saving a new draft revision in a newer schema.

Unknown metadata must not be silently discarded by adapters. New document types and fields must be able to coexist with older code in a fail-safe/preservation-oriented way.

### 11.4 Plain-text rendering

CORE is the authoritative renderer from structured document to `body`.

The renderer defines how each block becomes plain novel text. Production notes (`note`) may be excluded from the rendered public/plain manuscript according to the document rendering contract.

Search, ordinary MCP draft retrieval, and text export use `body` by default.

Detailed clients may explicitly request the structured document.

### 11.5 TipTap boundary

TipTap/ProseMirror is an editor implementation detail, not the persistence schema.

```text
TipTap JSON
   -> WEBUI editor adapter
NovelProduction Document Schema
   -> API
CORE validation + renderer
   -> SQLite
```

The reverse adapter reconstructs editor state from the NovelProduction document schema.

This keeps future editor replacement possible without rewriting stored draft history.

## 12. MCP adapter design

### 12.1 Stateless project addressing

MCP does not keep a mutable `selected_project` state.

Every project-scoped tool requires explicit `project_id`.

Example:

```text
episode_get(
  project_id="2126",
  episode_id=14
)
```

This avoids hidden state across chats, reconnects, Tunnel restarts, and concurrent clients.

### 12.2 Existing tools

Preserve existing Phase 1–3 MCP tool names and semantics where practical. Their implementation changes from direct Service/SQLite calls to HTTP requests.

Conceptually:

```text
episode_get
  -> GET /api/v1/projects/{project_id}/episodes/{episode_id}
```

New project-management tools:

```text
project_list(include_archived=false)
project_get(project_id)
project_create(working_title, project_id?)
project_update(project_id, status)
```

Do not add `project_select`.

### 12.3 Failure behavior

MCP uses `httpx` to call the API.

If API is unavailable:

```text
MCP -> BACKEND_UNAVAILABLE
```

There is no direct-DB fallback.

MCP maps the common API error contract to MCP structured errors without redefining business semantics.

## 13. WEBUI design

### 13.1 Technology

Frontend stack:

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- TipTap / ProseMirror
- dnd-kit
- shadcn/ui-style component primitives

Do not introduce Redux or another large global state store initially.

State responsibilities:

```text
URL / router state      -> project_id, current section, selected entity id
TanStack Query          -> API-backed server state/cache
React local state       -> unsaved form edits
TipTap editor state     -> active manuscript editor state
```

### 13.2 Navigation

Primary navigation uses a persistent left sidebar.

Initial sections:

```text
Dashboard
Structure
World
Characters
Timeline
Information
Manuscript
Canon / History
```

`Structure` provides the hierarchical tree:

```text
Chapter
  Episode
    Scene
```

### 13.3 Desktop and mobile editing layout

Desktop uses list/tree + right-side detail editing.

```text
sidebar | list/tree | detail/editor pane
```

On narrow/mobile layouts, selecting an item opens the detail/editor as a full-width screen rather than trying to preserve three columns.

### 13.4 Scope

The first full WEBUI target covers all data exposed by the current Phase 1–3 MCP feature set, including:

- work metadata;
- world facts;
- timeline events and event relations;
- characters and relationships;
- canon decisions/status;
- chapters, episodes, and scenes;
- episode references;
- character states;
- information items;
- reader disclosures;
- character knowledge;
- episode outline/context views;
- draft revisions and draft history.

### 13.5 Save and conflict UX

Forms use an explicit Save action rather than automatic save.

The form retains the entity version observed when editing began. If another client modifies the entity, the API returns `VERSION_CONFLICT`.

WEBUI then presents a comparison between:

- the user's unsaved edits;
- the latest database resource.

The initial UI does not attempt semantic auto-merge of prose or domain records.

## 14. Editor UX and metadata

The structured draft editor looks like a normal novel editor rather than a JSON editor.

Selecting a block exposes metadata in the detail/metadata pane.

Example dialogue metadata:

```text
Type: dialogue
Speaker: <character>
Addressees: <characters>
Scene: <scene>

Annotations
Emotion: optional
Intent: optional
Tags: optional
```

The UI may provide rich editing controls, but all persisted data passes through the WEBUI adapter into the independent NovelProduction document schema.

## 15. Runtime and LAN deployment

### 15.1 Production/common use

Source code remains logically separated, but common use runs one web/API process.

FastAPI serves:

```text
/api/v1/*  -> API routes
/*         -> WEBUI/frontend/dist static React build
```

Default bind:

```text
0.0.0.0:8765
```

The port is configurable. If the configured port is already in use, startup must fail explicitly rather than silently choosing another port.

Example addresses:

```text
Browser: http://192.168.x.x:8765/
MCP:     http://127.0.0.1:8765/api/v1/...
```

MCP remains a separate process. Tunnel processes, when used for ChatGPT Connector access, remain separate operational components.

### 15.2 Development

Development uses two processes for frontend HMR:

```text
Vite     :5173
FastAPI  :8765
```

Development CORS may allow the Vite origin. Production/common use is same-origin and does not require broad CORS.

### 15.3 Authentication/security boundary

Initial release has no authentication.

This is an explicit trusted-LAN design. Documentation must state that NovelProduction API/WEBUI must not be directly exposed to the public Internet.

## 16. Health and startup behavior

Provide at least:

```text
GET /api/v1/health
```

Minimal health response:

```json
{
  "status": "ok",
  "api_version": "v1"
}
```

This is a lightweight process/API liveness check. Heavier project/database diagnostics should be separate from the basic health endpoint.

Startup may verify configured directories and static assets, but it must not silently initialize, rewrite, delete, or migrate existing real story databases merely because the API process starts.

Project database creation/migration occurs through explicit project-creation/cutover operations.

## 17. Testing and CI

### 17.1 CORE

Cover:

- migration lifecycle;
- repository behavior;
- service validation;
- optimistic version checks;
- transaction boundaries;
- document schema validation;
- document render behavior;
- hash generation;
- project initialization;
- regression: search followed by write on supported flows.

### 17.2 API

Cover:

- `/api/v1` routing;
- project discovery;
- project create cleanup/failure atomicity;
- archive visibility and explicit archived access;
- project isolation;
- common error contract;
- HTTP 409 conflict mapping and latest-resource payload;
- one-request/one-connection behavior;
- view endpoint aggregation.

### 17.3 MCP

Cover:

- existing tool name/semantic preservation;
- required `project_id` on project-scoped tools;
- correct URL/project mapping;
- structured error mapping;
- `BACKEND_UNAVAILABLE` fail-closed behavior;
- no SQLite/direct-CORE runtime fallback.

### 17.4 WEBUI

Cover:

- API client behavior;
- project switching;
- list/detail navigation;
- explicit-save flows;
- version-conflict comparison UI;
- structure tree/reorder interactions;
- TipTap <-> NovelProduction document adapter round trips;
- metadata editing without loss of unknown fields.

### 17.5 End-to-end

Critical E2E scenarios include:

1. WEBUI/API/CORE create a new project and discover it.
2. Two projects can contain identical numeric entity IDs without cross-project leakage.
3. WEBUI reads an entity, MCP changes it, WEBUI save receives `VERSION_CONFLICT`.
4. Search followed by write succeeds in a fresh request model.
5. MCP calls API with explicit `project_id` and receives the same `project_id` in the result.
6. MCP fails closed when API is unavailable.
7. Structured draft JSON saves as a new append-only revision and renders deterministic `body` text.
8. React production build is served by the FastAPI process.

### 17.6 CI

CI should run at least:

```text
CORE tests
API tests
MCP tests
WEBUI tests
Python Ruff
Python mypy
TypeScript lint/typecheck
frontend build
E2E tests
```

The exact workflow split may be optimized later, but all layers must be exercised before merge.

## 18. Implementation/cutover sequence

### Phase A — CORE extraction

- Create `CORE/`.
- Move domain services, repositories, database lifecycle, and related errors/models out of `novel_mcp`.
- Move migrations 001–004 without changing SQL content.
- Temporarily keep MCP using CORE directly so current behavior can be regression-tested before adding HTTP.

Exit condition: existing Phase 1–3 behavior passes through CORE with no intended semantic changes.

### Phase B — API foundation

- Create `API/` FastAPI application.
- Add `/api/v1` and common error contract.
- Add project discovery/create/archive.
- Add fine-grained resource APIs and WEBUI query/view APIs.
- Formalize new-project initialization under CORE.
- Add migration 005 scaffolding as needed for structured drafts, but structured editor work may remain deferred to Phase E.

At the explicit cutover step, the current real story database may be backed up, deleted, and recreated under the new CORE lifecycle. Data migration from the old story content is not required by this design.

### Phase C — MCP HTTP adapter

- Convert MCP to `httpx` API calls.
- Preserve current tool names/semantics where practical.
- Add mandatory `project_id` to project-scoped tools.
- Add project-management tools.
- Remove runtime SQLite fallback.
- Refresh Tunnel/ChatGPT Connector action schema after tool schema changes.

Exit condition: ChatGPT -> MCP -> API -> CORE -> SQLite dogfood passes.

### Phase D — WEBUI

- Create React/Vite application.
- Implement project switching and project creation/archive.
- Implement sidebar, list/tree + detail layout, and responsive mobile behavior.
- Provide read/edit UI for the complete current Phase 1–3 data surface.
- Implement explicit save and conflict comparison.
- Implement aggregated view endpoints needed by the UI.

Exit condition: routine story administration and outline editing no longer require raw MCP calls.

### Phase E — Structured draft editor

- Finalize migration 005 structured draft columns.
- Implement NovelProduction Document Schema v1.
- Implement validation, rendering, document hash, and schema-version adapters in CORE.
- Implement TipTap editor adapter and metadata pane.
- Preserve append-only draft revision behavior.
- Keep `body` as the derived plain-text representation.

Exit condition: structured manuscript blocks and metadata round-trip WEBUI -> API -> CORE -> SQLite -> WEBUI, while MCP can retrieve normal plain text and optionally structured content.

## 19. Architectural invariants

The implementation must preserve these invariants:

1. SQLite remains the canonical story-data store.
2. At runtime, API -> CORE is the only supported story database access path.
3. WEBUI and MCP are independent API clients.
4. No server-global current-project state exists.
5. Every project-scoped MCP operation identifies `project_id` explicitly.
6. Project archive is organizational, not an authorization/read-only state.
7. Writes remain optimistic-version checked and transactional.
8. Existing draft revisions remain append-only.
9. Structured draft JSON is canonical when present; `body` is derived.
10. TipTap JSON is not the persistence contract.
11. Past document revisions are not rewritten for schema upgrades.
12. Production/common use may bundle API + static WEBUI into one process without coupling their source responsibilities.
13. Initial deployment is trusted-LAN only and unauthenticated.
14. Startup never silently mutates existing story databases.

## 20. Deferred follow-ups

The architecture intentionally leaves room for later work such as:

- Issue #5 narrative-node retirement semantics;
- Phase 4 continuity checks;
- richer timeline/relationship visualization;
- export pipelines;
- public/remote deployment with authentication;
- a dedicated reverse proxy/static server if deployment needs change;
- additional structured document block types and annotations;
- CLI or other clients using the same API.
