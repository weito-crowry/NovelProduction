# NovelProduction Phase C MCP HTTP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not use subagents, multi-agent delegation, parallel agent work, or model escalation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the 55 existing project-data MCP tools from direct CORE/SQLite access to a stateless HTTP adapter over the implemented FastAPI `/api/v1` contract, add four project-management tools, require explicit `project_id` on every project-scoped tool, and remove all MCP runtime fallback to CORE/SQLite.

**Architecture:** MCP becomes a pure async `httpx` client of API. One shared `ApiClient` is owned by the MCP server process and reused across tool calls; it never opens SQLite and never imports CORE. Existing tool names, descriptions, annotations, argument semantics, and result `data` semantics remain unchanged except that all 55 project-scoped tools gain required `project_id`, successful project-scoped results also identify the addressed project, and remote API errors are normalized into the MCP `ok/error` envelope. API remains the sole runtime path to CORE/SQLite.

**Tech Stack:** Python 3.10+ runtime, Python 3.13 CI/type-check target, MCP Python SDK 2.x, `httpx` async client, Pydantic v2 annotations already used by tool handlers, pytest, Ruff, mypy, pre-commit, existing FastAPI API started as a separate process for end-to-end smoke tests.

**Spec:** `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

**Tracking:** Issue #9, parent Epic #6.

## Global Constraints

- Codex/Luna executes this plan sequentially as a single agent. Do not spawn subagents, delegate investigation/review, perform parallel agent work, or escalate models.
- Base implementation on latest `origin/main`; the reviewed Phase B merge baseline is `dd2bc4acf39a64f1bc04be1be693ee8b50840c6d`.
- Existing Phase 1–3 tool names remain exactly the current 55 names. Do not rename or remove a project-data tool.
- Add exactly four project-management tools: `project_list`, `project_get`, `project_create`, `project_update`. Target MCP inventory after Phase C is exactly **59** tools.
- Every one of the existing 55 tools receives a required `project_id` argument. There is no default project, selected project, server-global project, `project_select`, or WEBUI-coupled state.
- Project-management semantics are: `project_list(include_archived=False)`, `project_get(project_id)`, `project_create(working_title, project_id=None)`, `project_update(project_id, status)` where status is `active|archived`.
- Keep existing read-only/destructive MCP annotations for the 55 tools. `project_list` and `project_get` are read-only/non-destructive; `project_create` is write/non-destructive; `project_update` is write/destructive.
- Project-scoped MCP success shape is `{"ok": true, "project_id": "<id>", "data": ...}`. The `data` value must be the same domain value represented by the Phase B API envelope; do not expose an extra nested API envelope.
- `project_list` success is `{"ok": true, "data": {"projects": [...]}}`. `project_get/create/update` include top-level `project_id` and put the API project summary in `data`.
- MCP remote-error shape is `{"ok": false, "error": {"code": ..., "message": ..., "project_id": ..., "details": {...}}}`. Preserve API `code`, safe `message`, `project_id`, and `details` when a valid API error envelope is returned.
- Network/connect/read timeout and other `httpx.RequestError` failures map to `BACKEND_UNAVAILABLE` with a safe message and no raw socket/URL exception text. Never fall back to SQLite/CORE.
- Malformed/unexpected HTTP response bodies map to safe `INTERNAL_ERROR`; do not leak traceback or raw response internals to MCP clients.
- For project-scoped 2xx responses, verify the API envelope `project_id` exactly matches the requested `project_id`. A mismatch is a protocol failure and must not be returned as successful data.
- Default MCP API URL is `http://127.0.0.1:8765`. Configuration precedence is CLI `--api-url` > `NOVEL_API_URL` > default.
- Use one shared `httpx.AsyncClient` per MCP server process, with a connect timeout no greater than 2 seconds and read/write timeout at least 10 seconds; use 30 seconds for read/write/pool to exceed the API/SQLite 5-second busy policy.
- MCP must not import `novel_core`, `sqlite3`, `novel_api`, FastAPI, or any API implementation module after cutover. HTTP JSON is the only runtime contract.
- Remove the runtime dependency `novel-production-core` from `MCP/pyproject.toml`; add `httpx>=0.28,<1.0` as a runtime dependency.
- Do not modify API domain semantics merely to simplify MCP. Phase C consumes the Phase B API contract as implemented.
- Do not add migration `005`; migrations `001`–`004` remain exact canonical blobs.
- Do not add WEBUI/React/Vite/TipTap code.
- Do not implement Issue #5 or Phase 4 continuity work.
- Do not touch the real `data/2126/story.db`, any stable story DB, production Tunnel, ChatGPT Connector, or running production MCP/API process during the implementation PR. Production cutover/dogfood happens only after review and merge.
- All implementation tests use mocks, temporary data roots, or temporary projects under a temporary API process.

---

## Target MCP Structure

```text
MCP/
├─ pyproject.toml
├─ src/novel_mcp/
│  ├─ __init__.py
│  ├─ api_client.py                 # async HTTP transport + protocol validation
│  ├─ config.py                     # API URL/timeout config only
│  ├─ mcp_server.py                 # MCP lifecycle; owns ApiClient, no DB
│  ├─ project_tool_descriptions.py
│  ├─ project_tools.py
│  ├─ tool_descriptions.py
│  ├─ phase1_tools.py
│  ├─ phase2_tool_descriptions.py
│  ├─ phase2_tools.py
│  ├─ phase3_tool_descriptions.py
│  ├─ phase3_tools.py
│  ├─ tool_errors.py                # remote/protocol/transport -> MCP error envelope
│  ├─ tool_support.py               # success/adaptation helpers
│  └─ tool_types.py                 # shared ProjectId/Limit/etc where useful
├─ tests/
│  ├─ test_api_client.py
│  ├─ test_project_mcp_tools.py
│  ├─ test_phase1_mcp_tools.py
│  ├─ test_phase2_mcp_tools.py
│  ├─ test_phase3_mcp_tools.py
│  ├─ test_http_adapter_e2e.py
│  ├─ test_phase3_stdio_smoke.py
│  └─ test_repository_checks.py
└─ scripts/
   ├─ check_repository_boundaries.py
   └─ check_source_size.py
```

The old MCP-local direct-DB compatibility files (`database.py`, CORE error facade, direct-DB initializer CLI, and Phase 3 DB acceptance helpers) are removed once their coverage has been replaced. Do not leave dead `novel_core` imports merely for compatibility.

---

## Canonical MCP -> HTTP Mapping

All project-data paths below are prefixed with `/api/v1/projects/{project_id}`.

### Phase 1 — 23 tools

| MCP tool | HTTP |
| --- | --- |
| `work_get` | `GET /work` |
| `work_update` | `PATCH /work` |
| `world_fact_create` | `POST /world-facts` |
| `world_fact_update` | `PATCH /world-facts/{fact_id}` |
| `world_fact_get` | `GET /world-facts/{fact_id}` |
| `world_fact_search` | `GET /world-facts/search?query=&limit=` |
| `timeline_event_create` | `POST /timeline/events` |
| `timeline_event_update` | `PATCH /timeline/events/{event_id}` |
| `timeline_event_get` | `GET /timeline/events/{event_id}` |
| `timeline_event_search` | `GET /timeline/events/search?query=&limit=` |
| `timeline_range` | `GET /timeline/range?start=&end=&limit=` |
| `timeline_move` | `POST /timeline/events/{event_id}/move` |
| `timeline_relation_create` | `POST /timeline/relations` |
| `character_create` | `POST /characters` |
| `character_update` | `PATCH /characters/{character_id}` |
| `character_get` | `GET /characters/{character_id}` |
| `character_search` | `GET /characters/search?query=&limit=` |
| `relationship_create` | `POST /relationships` |
| `relationship_update` | `PATCH /relationships/{relationship_id}` |
| `relationship_search` | `GET /relationships?character_id=&limit=` |
| `canon_status_set` | `POST /canon/status` |
| `canon_decision_get` | `GET /canon/decisions/{decision_id}` |
| `canon_decision_search` | `GET /canon/decisions/search?query=&limit=` |

### Phase 2 — 27 tools

| MCP tool | HTTP |
| --- | --- |
| `chapter_create` | `POST /chapters` |
| `chapter_update` | `PATCH /chapters/{chapter_id}` |
| `chapter_reorder` | `POST /chapters/{chapter_id}/reorder` |
| `chapter_list` | `GET /chapters` |
| `episode_create` | `POST /chapters/{chapter_id}/episodes` |
| `episode_update` | `PATCH /episodes/{episode_id}` |
| `episode_get` | `GET /episodes/{episode_id}` |
| `episode_reorder` | `POST /episodes/{episode_id}/reorder` |
| `episode_list` | `GET /chapters/{chapter_id}/episodes` |
| `scene_create` | `POST /episodes/{episode_id}/scenes` |
| `scene_update` | `PATCH /scenes/{scene_id}` |
| `scene_get` | `GET /scenes/{scene_id}` |
| `scene_reorder` | `POST /scenes/{scene_id}/reorder` |
| `scene_list` | `GET /episodes/{episode_id}/scenes` |
| `episode_reference_add` | `POST /episodes/{episode_id}/references` |
| `episode_reference_remove` | `DELETE /episodes/{episode_id}/references/{reference_type}/{target_id}` |
| `episode_reference_list` | `GET /episodes/{episode_id}/references?reference_type=` |
| `character_state_set` | `PUT /characters/{character_id}/states/{episode_id}` |
| `character_state_get` | `GET /characters/{character_id}/states/{episode_id}` |
| `character_state_history` | `GET /characters/{character_id}/states` |
| `information_create` | `POST /information` |
| `information_update` | `PATCH /information/{information_item_id}` |
| `information_get` | `GET /information/{information_item_id}` |
| `information_search` | `GET /information/search?query=&limit=` |
| `reader_disclosure_set` | `PUT /information/{information_item_id}/reader-disclosure` |
| `character_knowledge_set` | `PUT /characters/{character_id}/knowledge/{information_item_id}` |
| `character_knowledge_get` | `GET /characters/{character_id}/knowledge?episode_id=` |

### Phase 3 — 5 tools

| MCP tool | HTTP |
| --- | --- |
| `episode_outline_get` | `GET /episodes/{episode_id}/outline` |
| `episode_context` | `GET /episodes/{episode_id}/context` |
| `episode_draft_get` | `GET /episodes/{episode_id}/draft?revision=` |
| `episode_draft_save` | `POST /episodes/{episode_id}/drafts` |
| `episode_draft_history` | `GET /episodes/{episode_id}/drafts?limit=` |

### Project management — 4 new tools

| MCP tool | HTTP |
| --- | --- |
| `project_list` | `GET /api/v1/projects?include_archived=` |
| `project_get` | `GET /api/v1/projects/{project_id}` |
| `project_create` | `POST /api/v1/projects` |
| `project_update` | `PATCH /api/v1/projects/{project_id}` |

For JSON-body routes, use the existing MCP argument names that correspond to the Phase B Pydantic request schema. Path parameters are removed from the JSON body. Optional query parameters are omitted when their MCP value is `None`, rather than serialized as the string `"None"`.

---

### Task 1: Add the HTTP client, transport/protocol errors, and configuration

**Files:**
- Create: `MCP/src/novel_mcp/api_client.py`
- Rewrite: `MCP/src/novel_mcp/config.py`
- Modify: `MCP/src/novel_mcp/tool_errors.py`
- Modify: `MCP/src/novel_mcp/tool_support.py`
- Modify: `MCP/pyproject.toml`
- Regenerate: `MCP/uv.lock`
- Create: `MCP/tests/test_api_client.py`

**Interfaces:**
- `McpSettings(api_url: str, connect_timeout_seconds: float = 2.0, request_timeout_seconds: float = 30.0)`.
- `resolve_settings(api_url: str | None = None) -> McpSettings`, with CLI > `NOVEL_API_URL` > `http://127.0.0.1:8765` precedence.
- `ApiClient(settings: McpSettings, *, transport: httpx.AsyncBaseTransport | None = None)`.
- `await ApiClient.request_json(method, path, *, params=None, json_body=None) -> Any`.
- `await ApiClient.aclose() -> None`.
- `RemoteApiError`: parsed non-2xx API error with `status_code`, `code`, `message`, `project_id`, `details`.
- `BackendUnavailableError`: network/timeout failure; no raw exception is exposed to callers.
- `BackendProtocolError`: malformed JSON, invalid error envelope, invalid project envelope, or project-ID mismatch.
- `project_success(payload, requested_project_id)` unwraps `{"project_id": ..., "data": ...}` to MCP success shape.
- `project_failure(exc, requested_project_id)` produces safe MCP error shape.

- [ ] **Step 1: Write failing API-client tests** covering base URL normalization, query/body forwarding, successful JSON, valid API error parsing, connection failure -> `BACKEND_UNAVAILABLE`, malformed JSON -> protocol error, and project-ID mismatch rejection.

```python
async def test_project_envelope_rejects_mismatched_project_id() -> None:
    payload = {"project_id": "other", "data": {"id": 1}}
    with pytest.raises(BackendProtocolError):
        project_success(payload, "2126")
```

- [ ] **Step 2: Run the focused tests and confirm RED.**

```powershell
Set-Location MCP
uv run pytest tests/test_api_client.py -q
```

Expected: imports/types are absent and tests fail.

- [ ] **Step 3: Implement `McpSettings`, `ApiClient`, remote error parsing, safe transport failure mapping, and envelope adapters.** Use `httpx.Timeout(30.0, connect=2.0)` or equivalent explicit values. Do not retry writes automatically.

- [ ] **Step 4: Add runtime `httpx>=0.28,<1.0` and regenerate the MCP lock without unrelated dependency upgrades.** Keep `novel-production-core` temporarily until Task 6 so intermediate commits remain testable; it is removed in Task 6.

- [ ] **Step 5: Run focused tests, Ruff, and mypy.**

```powershell
uv run pytest tests/test_api_client.py -q
uv run ruff check src/novel_mcp/api_client.py src/novel_mcp/config.py src/novel_mcp/tool_errors.py src/novel_mcp/tool_support.py tests/test_api_client.py
uv run mypy src
```

- [ ] **Step 6: Commit.**

```powershell
git add MCP
git commit -m "feat: add MCP HTTP client foundation"
```

---

### Task 2: Add project-management MCP tools and lock the new tool contract

**Files:**
- Create: `MCP/src/novel_mcp/project_tool_descriptions.py`
- Create: `MCP/src/novel_mcp/project_tools.py`
- Create or modify: `MCP/src/novel_mcp/tool_types.py`
- Modify: `MCP/src/novel_mcp/mcp_server.py`
- Create: `MCP/tests/test_project_mcp_tools.py`
- Modify: existing MCP tool-inventory/schema tests.

**Interfaces:**

```python
ProjectId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$",
    ),
]
```

Handlers:

```python
async def project_list(include_archived: bool = False) -> dict[str, Any]: ...
async def project_get(project_id: ProjectId) -> dict[str, Any]: ...
async def project_create(
    working_title: Annotated[str, Field(min_length=1)],
    project_id: ProjectId | None = None,
) -> dict[str, Any]: ...
async def project_update(
    project_id: ProjectId,
    status: Literal["active", "archived"],
) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write failing tests** for the four tool schemas, descriptions, annotations, request mappings, response shapes, `project_id` validation, and total inventory `59` with no `project_select`.

- [ ] **Step 2: Run focused tests and confirm RED.**

```powershell
uv run pytest tests/test_project_mcp_tools.py -q
```

- [ ] **Step 3: Implement project tools** using only `ApiClient`; do not import project registry or API schemas.

- [ ] **Step 4: Register project tools in `mcp_server.py`** and define `PROJECT_TOOL_NAMES`. `ALL_TOOL_NAMES` must become 59 names.

- [ ] **Step 5: Run focused tests and existing inventory tests.**

- [ ] **Step 6: Commit.**

```powershell
git add MCP
git commit -m "feat: add MCP project management tools"
```

---

### Task 3: Convert all 23 Phase 1 tools to HTTP with required `project_id`

**Files:**
- Rewrite: `MCP/src/novel_mcp/phase1_tools.py`
- Modify: `MCP/tests/test_phase1_mcp_tools.py`
- Modify: Phase 1 acceptance tests that currently construct CORE services directly; replace transport-specific expectations with HTTP-adapter expectations while preserving domain-behavior coverage in CORE/API.

**Interfaces:**
- `register_phase1_tools(client: ApiClient, register: Registrar) -> None`.
- Every one of the 23 handlers has `project_id: ProjectId` as a required first argument.
- Use the canonical Phase 1 mapping table above exactly.
- JSON-like MCP inputs (`themes_json`, `details_json`, `profile_json`) must preserve current accepted input semantics. Convert a JSON string to a JSON value before sending when the API request schema expects JSON; reject invalid JSON as `VALIDATION_ERROR` locally rather than silently changing it.

- [ ] **Step 1: Replace/extend tests with a table-driven 23-tool contract test.** For every tool assert HTTP method, formatted path, query parameters or JSON body, and unwrapped project-scoped result.

- [ ] **Step 2: Add explicit tests** for `work_get(project_id=...)`, Japanese `world_fact_search`, Japanese `character_search`, stale `VERSION_CONFLICT` details preservation, and `relationship_search(character_id=None)` omitting the optional query key.

- [ ] **Step 3: Run Phase 1 MCP tests and confirm RED.**

- [ ] **Step 4: Rewrite Phase 1 handlers as HTTP calls.** Do not call `call_service`, CORE services, or SQLite.

- [ ] **Step 5: Run Phase 1 tests plus API-client tests.**

- [ ] **Step 6: Commit.**

```powershell
git add MCP/src/novel_mcp/phase1_tools.py MCP/tests
git commit -m "refactor: route Phase 1 MCP tools through HTTP"
```

---

### Task 4: Convert all 27 Phase 2 tools to HTTP with required `project_id`

**Files:**
- Rewrite: `MCP/src/novel_mcp/phase2_tools.py`
- Modify: `MCP/tests/test_phase2_mcp_tools.py`
- Modify/replace direct-CORE Phase 2 canon/acceptance tests only where they are transport-specific.

**Interfaces:**
- `register_phase2_tools(client: ApiClient, register: Registrar) -> None`.
- All 27 handlers require `project_id: ProjectId` first.
- Use the canonical Phase 2 mapping table above exactly.
- `episode_reference_remove` uses path parameters, not a JSON request body.
- `episode_reference_list(reference_type=None)` omits the optional query parameter.
- Character state/knowledge/disclosure write fields retain current MCP names and optional-version semantics.

- [ ] **Step 1: Add a table-driven 27-tool mapping test** and focused tests for delete/reference paths, reorder conflict preservation, optional query omission, and state/knowledge version conflicts.

- [ ] **Step 2: Run Phase 2 tests and confirm RED.**

- [ ] **Step 3: Rewrite Phase 2 handlers to HTTP.** Preserve existing Pydantic constraints and read-only/destructive annotations.

- [ ] **Step 4: Run Phase 2 tests and the shared API-client tests.**

- [ ] **Step 5: Commit.**

```powershell
git add MCP/src/novel_mcp/phase2_tools.py MCP/tests
git commit -m "refactor: route Phase 2 MCP tools through HTTP"
```

---

### Task 5: Convert all 5 Phase 3 authoring tools to HTTP

**Files:**
- Rewrite: `MCP/src/novel_mcp/phase3_tools.py`
- Modify: `MCP/tests/test_phase3_mcp_tools.py`
- Replace direct-DB Phase 3 adapter regressions with HTTP-adapter regressions.

**Interfaces:**
- `register_phase3_tools(client: ApiClient, register: Registrar) -> None`.
- All five tools require `project_id: ProjectId` first.
- Draft GET uses optional `revision` query; omit it when `None`.
- Draft history uses `limit` query.
- Draft save body fields remain `body`, `expected_parent_draft_id`, `source_agent`, `change_summary`.
- Preserve API `VERSION_CONFLICT` details including latest draft snapshot.

- [ ] **Step 1: Add failing mapping tests for all five operations** and focused stale-parent CAS test.

- [ ] **Step 2: Run Phase 3 MCP tests and confirm RED.**

- [ ] **Step 3: Rewrite the five handlers to HTTP.** Remove the `run_phase3_acceptance` wrapper from the runtime tool module; DB-level qualification is not an MCP runtime responsibility after the cutover.

- [ ] **Step 4: Run Phase 3 tests and ensure ordinary draft retrieval still returns the plain `body` representation supplied by API.**

- [ ] **Step 5: Commit.**

```powershell
git add MCP/src/novel_mcp/phase3_tools.py MCP/tests
git commit -m "refactor: route Phase 3 MCP tools through HTTP"
```

---

### Task 6: Remove direct CORE/SQLite runtime dependencies and implement MCP HTTP lifecycle

**Files:**
- Rewrite: `MCP/src/novel_mcp/mcp_server.py`
- Delete: `MCP/src/novel_mcp/database.py`
- Delete: `MCP/src/novel_mcp/errors.py` if no transport-independent MCP type still requires it.
- Delete: `MCP/src/novel_mcp/cli.py` and remove the direct-DB `novel-init` entry point, unless it has first been rewritten as a pure HTTP client; do not retain any direct-DB initializer inside `novel_mcp`.
- Delete: `MCP/src/novel_mcp/phase3_acceptance.py`, `phase3_acceptance_seed.py`, `phase3_acceptance_probes.py` after equivalent safety coverage is retained in CORE/API and Task 7 MCP HTTP E2E tests.
- Modify: `MCP/pyproject.toml`
- Regenerate: `MCP/uv.lock`
- Modify: `MCP/tests/test_development_foundation.py`, `test_novel_init.py`, Phase 3 acceptance tests as required by the intentional boundary change.

**Interfaces:**
- `create_server(settings: McpSettings, *, transport: httpx.AsyncBaseTransport | None = None) -> NovelMCPServer`.
- `NovelMCPServer` owns one `ApiClient` and provides `async aclose()`.
- Main parser accepts `--api-url`; it no longer accepts `--db` or `--migration-dir`.
- Runtime config precedence is `--api-url` > `NOVEL_API_URL` > `http://127.0.0.1:8765`.
- Main runs MCP and closes the shared `AsyncClient` in the same `asyncio.run()` lifecycle.

- [ ] **Step 1: Add failing server lifecycle tests** proving no DB is opened at server creation, the shared HTTP client is closed, CLI/API URL precedence works, and old DB arguments are no longer part of the server runtime interface.

- [ ] **Step 2: Rewrite `mcp_server.py`** to remove `sqlite3`, `DatabaseConfig`, `open_database`, all CORE service imports, and `ServiceContainer`.

- [ ] **Step 3: Remove `novel-production-core` from MCP runtime dependencies and `[tool.uv.sources]`; regenerate lock.** `httpx` remains runtime dependency.

- [ ] **Step 4: Remove direct-CORE compatibility/acceptance modules and replace tests rather than deleting behavior coverage.** CORE/API retain domain/migration/append-only/context safety tests; MCP keeps adapter/E2E checks.

- [ ] **Step 5: Run the entire MCP suite.**

```powershell
Set-Location MCP
uv sync --all-groups
uv run pytest -W error
```

- [ ] **Step 6: Commit.**

```powershell
git add -A MCP
git commit -m "refactor: remove MCP direct database runtime"
```

---

### Task 7: Add real MCP -> HTTP API -> CORE -> temporary SQLite end-to-end coverage

**Files:**
- Create: `MCP/tests/test_http_adapter_e2e.py`
- Rewrite/adapt: `MCP/tests/test_phase3_stdio_smoke.py`
- Modify: test helpers only; do not import `novel_api` into `novel_mcp` runtime source.

**Test topology:**

```text
pytest / MCP client
  -> MCP handlers or stdio MCP subprocess
  -> http://127.0.0.1:<ephemeral-port>
  -> real `novel-api` subprocess from `../API`
  -> CORE
  -> temporary data root/story.db
```

The test may launch the API with `uv run --project ../API novel-api --data-root <tmp> --host 127.0.0.1 --port <ephemeral>` and wait on `/api/v1/health`. It must terminate the subprocess in `finally`, even on failure.

- [ ] **Step 1: Add a real E2E test** that creates two temporary projects through MCP, writes a different world fact to each, searches each project, and proves no cross-project data leakage.

- [ ] **Step 2: Add public search -> write regression through MCP HTTP path:** create world fact -> search it -> update it with returned version -> verify updated result.

- [ ] **Step 3: Add VERSION_CONFLICT regression through MCP HTTP path** and assert `error.code`, `error.project_id`, expected/current versions, and `current_resource` survive adaptation.

- [ ] **Step 4: Add Phase 3 context/draft smoke** through HTTP: outline/context read, draft save/get/history, stale-parent CAS failure. Use only temporary project data.

- [ ] **Step 5: Add `BACKEND_UNAVAILABLE` regression:** stop/use unreachable backend, call a project tool, assert safe structured error, and prove no file/SQLite fallback appears.

- [ ] **Step 6: Adapt stdio smoke** to start MCP with `--api-url`, list exactly 59 tools, inspect a representative project-scoped schema for required `project_id`, and execute at least `project_list` plus `work_get` against the temporary API.

- [ ] **Step 7: Run the focused E2E/stdio tests and then full MCP tests.**

- [ ] **Step 8: Commit.**

```powershell
git add MCP/tests
git commit -m "test: verify MCP HTTP adapter end to end"
```

---

### Task 8: Strengthen CI/boundary checks and document the post-merge cutover

**Files:**
- Modify: `MCP/scripts/check_repository_boundaries.py`
- Modify: `MCP/scripts/check_source_size.py` only if new files require normal inventory updates; do not raise thresholds.
- Modify: `.github/workflows/mcp-ci.yml`
- Modify: `README.md`
- Create: `docs/runbooks/phase-c-mcp-http-cutover.md` if no equivalent runbook exists.

**Boundary requirements to enforce mechanically:**

- `MCP/src` has no import of `novel_core`, `sqlite3`, `novel_api`, or FastAPI.
- `MCP/pyproject.toml` does not depend on `novel-production-core` or `novel-production-api`.
- No `project_select` tool/string is registered.
- Tool inventory is exactly 59: 4 project + 23 Phase 1 + 27 Phase 2 + 5 Phase 3.
- Every one of the existing 55 project-data tool schemas requires `project_id`.
- migrations 001–004 remain exact; migration 005 absent.
- API remains API -> CORE; no reverse API dependency is introduced.

**Cutover runbook must state that implementation PR does not touch production. After merge/review only:**

1. update local main to the merged Phase C revision;
2. start `novel-api` on `127.0.0.1/0.0.0:8765` with the intended `data` root;
3. verify `/api/v1/health` and `/api/v1/projects`;
4. start MCP with `NOVEL_API_URL=http://127.0.0.1:8765` or `--api-url`;
5. refresh/reconnect the ChatGPT Connector so the 59-tool schema and required `project_id` fields are visible;
6. keep the current Tunnel route unchanged unless its MCP process address actually changes;
7. dogfood `project_list`, `project_get`, `work_get(project_id="2126")`, one search/read operation, and a controlled write only if separately approved;
8. verify API/MCP logs identify the same `project_id` and no direct DB fallback occurs;
9. if cutover fails, stop the new MCP/API processes and restore the prior runtime process/config; do not repair/reset the DB as a rollback mechanism.

- [ ] **Step 1: Write/extend repository-check tests and make them fail on current direct-CORE patterns.**

- [ ] **Step 2: Implement boundary and CI checks without weakening existing checks.**

- [ ] **Step 3: Update README/runtime commands and write the cutover runbook.** Clearly distinguish implemented Phase C code from the not-yet-executed production cutover.

- [ ] **Step 4: Run repository checks, source-size, and workflow-local commands.**

- [ ] **Step 5: Commit.**

```powershell
git add .github MCP/scripts MCP/tests README.md docs/runbooks
git commit -m "ci: enforce MCP HTTP-only runtime boundary"
```

---

### Task 9: Full verification, Draft PR, and handoff for ChatGPT review

**Files:** No new feature scope. Only fix defects found by verification; do not broaden Phase C.

- [ ] **Step 1: Verify CORE remains green.**

```powershell
Set-Location CORE
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_core --cov-report=term-missing
```

- [ ] **Step 2: Verify API remains green.**

```powershell
Set-Location ../API
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_api --cov-report=term-missing
```

- [ ] **Step 3: Verify MCP.**

```powershell
Set-Location ../MCP
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_mcp --cov-report=term-missing
uv run pre-commit run --all-files
```

- [ ] **Step 4: Verify repository invariants from repository root.**

```powershell
Set-Location ..
python MCP/scripts/check_source_size.py
python MCP/scripts/check_repository_boundaries.py
git diff --check
git status --short
```

Also explicitly verify:

- 59 MCP tools exactly;
- no `project_select`;
- required `project_id` on all 55 project-data tools;
- `novel_core`, `sqlite3`, and `novel_api` absent from `MCP/src` imports;
- `novel-production-core` absent from MCP runtime dependencies/lock as a direct package dependency;
- `httpx` present as MCP runtime dependency;
- migrations 001–004 exact canonical identities, 005 absent;
- real `data/2126/story.db` not opened/modified by tests or implementation;
- temporary real E2E and stdio smoke pass;
- worktree clean after commits.

- [ ] **Step 5: Push the feature branch and create a Draft PR.**

Suggested title:

```text
[Issue #9] Convert MCP to stateless HTTP adapter
```

PR body must include:

- `Refs #9`, parent `#6`;
- base `origin/main` and final HEAD;
- tool inventory `55 -> 59`;
- explicit `project_id` schema change summary;
- project tool list;
- MCP success/error envelope changes;
- API URL configuration/default;
- HTTP timeout/failure semantics;
- proof that MCP no longer imports/dependencies on CORE/SQLite/API code;
- Phase 1/2/3 mapping coverage counts `23/27/5`;
- multi-project E2E, search -> write, VERSION_CONFLICT, draft CAS, `BACKEND_UNAVAILABLE`, and stdio smoke results;
- CORE/API/MCP test counts and coverage;
- Ruff/format/mypy/pre-commit/source-size/boundary results;
- migrations unchanged and 005 absent;
- real DB/Tunnel/Connector untouched;
- post-merge cutover still pending and linked runbook.

- [ ] **Step 6: Do not merge.** Return the PR and verification report to ChatGPT for GitHub review. Phase C Issue #9 remains open until the reviewed implementation is merged, main CI is green, and the post-merge Connector/Tunnel/API dogfood is completed.

---

## Self-Review Checklist

- Spec coverage: MCP -> HTTP dependency direction, explicit project IDs, project tools, no hidden selection state, no fallback, error preservation, backend unavailable behavior, API URL, and post-merge dogfood are all assigned to tasks.
- Interface count: `4 + 23 + 27 + 5 = 59` tools.
- Existing 55 tool names are unchanged; only required `project_id` is added.
- The mapping table uses the actual Phase B routes merged in PR #14 rather than guessed endpoints.
- No migration, WEBUI, Issue #5, Phase 4, project deletion, authentication, or public-Internet work is included.
- Runtime MCP has no CORE/API implementation import after Task 6.
- Production data/Tunnel/Connector mutation is explicitly deferred until after merge/review.
- No placeholder/TBD implementation steps remain.
