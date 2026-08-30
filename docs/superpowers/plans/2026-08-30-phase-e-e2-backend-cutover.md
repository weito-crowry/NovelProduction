# Phase E E2 Backend Cutover Implementation Plan

> **For agentic workers:** This plan is executed by a single Codex agent only. No subagents, no delegation, no parallel agent work, and no model escalation are permitted. Steps use checkbox syntax and are executed sequentially. ChatGPT reviews the pushed integration branch after execution.

**Goal:** Replace legacy draft `body` persistence with transactional Canonical Document storage and expose the approved structured draft contract through CORE, API, context, and the existing MCP tools.

**Architecture:** Migration 005 destructively replaces the legacy `drafts` table on the isolated Phase E integration line. CORE owns structural parsing, parent-relative authoring, metadata semantics, live-reference validation, CAS, restore, projections, and export; the repository stores only the canonical serialized document and the API/MCP layers remain thin adapters. All tests use disposable databases or existing non-Manuscript fixtures; stable `data/2126`, the stable runtime, and the Phase E-excluded WEBUI Manuscript flow remain untouched.

**Tech Stack:** Python 3.10+, SQLite, `novel_core`, FastAPI/Pydantic, HTTPX, MCP Python SDK, pytest, Ruff, Mypy, uv, npm/Playwright, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-30-novelproduction-phase-e-structured-manuscript-design.md` and `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

## Global Constraints

- Work only in `C:\Users\weito\Documents\src\NovelProduction-phase-e-integration` on branch `codex/phase-e-integration`, based on `618ad6b231c06302f910cef3a35fa416f52d6699`.
- `MCP/.tools/` and ignored `WEBUI/frontend/test-results/` in the stable checkout are user-owned and must not be modified, removed, or restored.
- Never open, migrate, hash, copy, or write stable `C:\Users\weito\Documents\src\NovelProduction\data\2126\story.db`.
- Phase E runtime data must use an explicit disposable root such as `C:\Users\weito\Documents\src\NovelProduction-phase-e-integration\.tmp\phase-e-data`; never inherit the stable `NOVEL_DATA_ROOT`.
- Migrations `001_initial.sql` through `004_drafts.sql` are immutable; only `005_structured_drafts.sql` is added on this line.
- The MCP tool inventory remains exactly 59: extend existing draft/context tools and add no tools.
- The E2 boundary excludes WEBUI Manuscript Phase E conversion, TipTap integration, Read-first UI, and Save/Cancel editor integration.
- Every logical implementation change follows RED (a new test fails for the intended reason), GREEN (minimal implementation passes), adjacent regression tests, then a logical commit.
- `plain_text`, `html`, `metadata_updates`, and `restore_revision` distinguish omitted/`None` from supplied empty strings or empty objects; API-to-CORE conversion must preserve presence.
- Stored invalid Canonical Documents map to `DocumentStorageError`/`DOCUMENT_STORAGE_ERROR`; caller schema violations map to `DocumentSchemaError`/`DOCUMENT_SCHEMA_ERROR`; semantic command errors map to `ValidationError`; numeric stale CAS alone maps to `VersionConflictError`.
- Do not add legacy `body` compatibility, API v2 duplication, migration backfill, live Broker/Tunnel changes, or E3/E4/E5 implementation.

## File map

- `CORE/migrations/005_structured_drafts.sql`: exact destructive replacement schema, constraints, index, and append-only triggers.
- `CORE/src/novel_core/repositories/draft_repository.py`: raw storage records and metadata-only history queries; no Document parsing.
- `CORE/src/novel_core/document/authoring.py`: database-independent plain import and parent-relative Restricted HTML/metadata resolution.
- `CORE/src/novel_core/services/draft_service.py`: parsed draft snapshots, save state machine, CAS, live references, restore, and transaction verification.
- `CORE/src/novel_core/services/context_service.py`, `models/context.py`, `services/context_projection.py`, and `repositories/context_repository.py`: structured previous-draft context using the existing E1 projection.
- `CORE/src/novel_core/errors.py` and `document/__init__.py`: storage error and public authoring exports.
- `CORE/tests/test_database_lifecycle.py`, `test_installed_wheel.py`, `test_draft_service.py`, `test_context_service.py`, plus focused new authoring/migration tests: executable CORE contract.
- `API/src/novel_api/schemas/authoring.py`, `routes/authoring.py`, and `errors.py`: DraftSave presence-aware request model, GET/save/history/export routes, and explicit error mappings.
- `API/tests/test_phase3_api.py`, `test_errors.py`, `test_views.py`, plus focused Phase E API tests: HTTP contract and non-Manuscript regression coverage.
- `MCP/src/novel_mcp/phase3_tools.py`, `phase3_tool_descriptions.py`, and `api_client.py`: existing-tool contract and repeated query forwarding.
- `MCP/tests/test_phase3_http_adapter.py`, `test_phase3_mcp_tools.py`, `test_http_adapter_e2e.py`, and repository checks: adapter, error, and exact 59-tool coverage.
- `.github/workflows/mcp-ci.yml`: exact 001–005 inventory while preserving the existing 001–004 blob SHA assertions and immutability guards.
- `docs/superpowers/specs/...` and `docs/superpowers/plans/...`: approved clarification and execution-plan records only.

### Task 1: Isolation, contract synchronization, plan, and migration test scaffolding

**Files:**
- Modify: `docs/superpowers/specs/2026-08-30-novelproduction-phase-e-structured-manuscript-design.md`
- Modify: `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`
- Create: `docs/superpowers/plans/2026-08-30-phase-e-e2-backend-cutover.md`
- Test: `CORE/tests/test_database_lifecycle.py`, `CORE/tests/test_installed_wheel.py`, and the focused migration tests added in Task 2

**Interfaces:**
- Consumes: approved Phase E/E2 clarification and the stable baseline preflight.
- Produces: authoritative clarification text, the exact E2 plan, an isolated branch/worktree, and test scaffolding that uses disposable databases.

- [x] Confirm `origin/main == 618ad6b231c06302f910cef3a35fa416f52d6699`, the stable checkout branch/dirty state, stable API/MCP/Tunnel process roots, stable port 8765, and empty shell `NOVEL_DATA_ROOT` without stopping processes.
- [x] Create or safely reuse the sibling worktree at `C:\Users\weito\Documents\src\NovelProduction-phase-e-integration` on `codex/phase-e-integration` from `origin/main`; do not delete or reset an existing worktree.
- [x] Append only the E2 clarification section covering heading transitions, presence-aware metadata, command taxonomy, exact migration constraints, inserted-row precommit validation, runtime isolation, conflict projection, restore revision-number semantics, and the temporary E2E boundary.
- [x] Add only the architecture error-table row `500 | DOCUMENT_STORAGE_ERROR | Persisted Canonical Document is structurally invalid`.
- [x] Save this plan with the single-agent/sequential/no-escalation/ChatGPT-review constraints before implementation.
- [x] Run `git diff --check` and inspect `git diff --name-only` to confirm documentation-only changes at this boundary.

### Task 2: Migration 005 and CI/package migration invariants

**Files:**
- Create: `CORE/migrations/005_structured_drafts.sql`
- Modify: `.github/workflows/mcp-ci.yml`
- Modify: `CORE/tests/test_database_lifecycle.py`
- Modify: `CORE/tests/test_installed_wheel.py`
- Create or modify: focused migration regression tests under `CORE/tests/`

**Interfaces:**
- Consumes: migration runner `apply_migrations`, `default_migration_dir`, and the unchanged 001–004 scripts.
- Produces: a migration inventory containing exactly 001–005 and a new `drafts` table with `document_json` as the only manuscript content.

- [ ] Write failing fresh-database and populated-legacy migration tests. Apply 001–004, insert `r1 -> r2 -> r3` while foreign keys remain enabled, apply 005, and assert old rows disappear, new rows are empty, `body`/`content_hash` are absent, `document_json` exists, ledger 005 is recorded, integrity is `ok`, and the exact uniqueness/FK definitions are present.
- [ ] Add failing tests that update/delete a new draft through SQLite and verify the append-only triggers reject both operations; assert the migration SQL contains the required trigger-drop/null-parent/delete/drop/create/index/trigger order and never disables foreign keys.
- [ ] Run the focused migration tests and confirm RED is caused by missing `005_structured_drafts.sql`/new schema rather than a test defect.
- [ ] Implement `005_structured_drafts.sql` with `document_json TEXT NOT NULL CHECK(json_valid(document_json))`, source-agent and summary bounds, exact three UNIQUE constraints, exact episode `ON DELETE CASCADE` FK, exact parent `ON DELETE RESTRICT` FK, revision index, and append-only triggers.
- [ ] Update only the expected migration list in `.github/workflows/mcp-ci.yml` to include `005_structured_drafts.sql`; retain the four existing blob SHA assertions, `MCP/migrations` guard, clean-tree guard, and stable-data guard.
- [ ] Extend the installed-wheel test so a built/installed `novel_core` wheel exposes exactly 001–005 from the packaged migration directory and initializes a disposable database through 005; do not accept source-checkout visibility.
- [ ] Run focused migration/package tests and then `uv run --locked pytest CORE/tests/test_database_lifecycle.py CORE/tests/test_installed_wheel.py`; commit the migration/invariant boundary.

### Task 3: DraftRepository structured persistence

**Files:**
- Modify: `CORE/src/novel_core/repositories/draft_repository.py`
- Modify: `CORE/tests/test_draft_service.py` or create `CORE/tests/test_draft_repository.py`
- Update: any existing migration-shaped test fixtures that still issue legacy draft INSERTs

**Interfaces:**
- Consumes: the Task 2 schema.
- Produces: `DraftRecord(id, work_id, episode_id, revision, parent_draft_id, document_json, source_agent, change_summary, created_at)`, `DraftMetadata(id, episode_id, revision, parent_draft_id, source_agent, change_summary, created_at)`, and `insert(..., document_json: str) -> int`.

- [ ] Write failing repository tests asserting raw records have `document_json` and no `body`/`content_hash`, history has no content/hash/character-count fields, history selects newest N but returns that window oldest-to-newest, and the repository never imports/calls the Document parser.
- [ ] Run the focused repository tests and observe the expected missing-field/signature failures.
- [ ] Replace column projections and INSERT arguments with the exact structured fields. Keep `begin_write`, `commit`, `rollback`, latest/get, and history ordering unchanged.
- [ ] Run repository tests and the adjacent database/draft tests; commit only repository and directly required fixtures.

### Task 4: Parent-relative Document authoring engine

**Files:**
- Create: `CORE/src/novel_core/document/authoring.py`
- Modify: `CORE/src/novel_core/document/__init__.py`
- Modify: `CORE/src/novel_core/errors.py` only if a shared authoring error type is required by the existing taxonomy
- Create: `CORE/tests/test_document_authoring.py`
- Preserve: E1 document model/schema/HTML parser behavior unless a focused clarification test proves a necessary compatibility correction

**Interfaces:**
- Consumes: `NovelDocument`, `NovelBlock`, `BlockAttrs`, `AuthoringBlockInput`, `parse_authoring_html`, `parse_document_json`, `normalize_document`, `serialize_document_json`, and `new_block_id`.
- Produces: a DB-independent authoring API equivalent to `import_plain_text(text) -> NovelDocument` and `resolve_authoring(parent, html, metadata_updates) -> AuthoringResolution(document, id_map)`; exact public names may follow existing naming but must remain explicit in `document/__init__.py`.

- [ ] Write failing tests for CRLF/CR normalization, surrounding blank-line trimming, whitespace-only separators, single-newline `<br>`, HTML escaping, narration-only blocks, empty input, and preservation of meaningful internal whitespace.
- [ ] Write failing tests for complete HTML snapshot deletion/reordering, retained formal IDs, same-request correlation IDs and `id_map`, id-less ID generation, no resurrection of deleted historical IDs, existing/new `<p>` type inheritance/defaults, forced tags, and note inclusion.
- [ ] Write failing tests for heading-level required/cleared semantics, h1/h2/h3 same-value and conflict behavior, scene/speaker inheritance/set/clear, annotation inheritance/replacement/null/removal, complex JSON preservation, ID target validity, empty individual patches, empty metadata-only commands, and all self-conflicts.
- [ ] Run each focused authoring test group and confirm RED for the missing parent-relative resolver and plain importer.
- [ ] Implement the smallest pure authoring module: parse/normalize plain text, parse full Restricted HTML once, reconcile current-parent IDs only, maintain a correlation map, apply explicit-vs-omitted metadata operations, enforce heading/type invariants, reject semantic self-conflicts, and finish with `normalize_document`.
- [ ] Keep database/reference lookup out of the module. Do not parse or validate stored rows in the repository.
- [ ] Run `uv run pytest CORE/tests/test_document_authoring.py CORE/tests/test_document_schema.py CORE/tests/test_document_authoring_html.py CORE/tests/test_document_projections.py`; commit the pure authoring boundary.

### Task 5: DraftService, CAS, restore, and live-reference validation

**Files:**
- Modify: `CORE/src/novel_core/services/draft_service.py`
- Modify: `CORE/src/novel_core/errors.py` to add `DocumentStorageError(code="DOCUMENT_STORAGE_ERROR")`
- Modify: `CORE/tests/test_draft_service.py`
- Create or modify: focused storage-corruption/transaction tests under `CORE/tests/`

**Interfaces:**
- Consumes: Task 3 raw records and Task 4 authoring functions.
- Produces: parsed `DraftSnapshot`-style domain values, `save_draft(episode_id, *, plain_text=None, html=None, metadata_updates=None, restore_revision=None, expected_parent_draft_id=None, source_agent=None, change_summary="")`, structured `get_draft`, metadata-only `history`, and deterministic `DraftSaveResult`/ID-map data.

- [ ] Write failing tests for initial plain/html exclusivity, empty-string saves, plain-plus-metadata rejection, existing-save mode requirements, null/omitted parent semantics, numeric stale CAS, explicit HTML no-op append, and no partial revision after all rejected commands.
- [ ] Write failing tests for restore by episode revision number (not draft row ID), missing target validation, metadata replacement on restored revision, historical structural-only reads, unchanged live refs not revalidated, changed/new scene/speaker live reference checks, and separate storage corruption wrapping.
- [ ] Write a failing transaction test that corrupts/monkeypatches the inserted-row reload or parser and proves rollback occurs before commit; the service must validate inserted ID/revision/document inside the transaction.
- [ ] Run the focused service tests and confirm RED against the legacy body-only service.
- [ ] Implement request validation and the exact state machine. Use `BEGIN IMMEDIATE`, latest/CAS, parent parse, authoring or historical resolution, changed-reference validation, canonical serialization, INSERT, same-transaction reload/parse/identity checks, COMMIT, and only then return.
- [ ] Parse every stored `record.document_json` at the DraftService boundary; wrap only `DocumentSchemaError` from stored content as `DocumentStorageError`, never repair it, and use structural-only validation for history/restore.
- [ ] Run focused service tests plus all adjacent CORE service tests; commit the DraftService boundary.

### Task 6: Structured context integration

**Files:**
- Modify: `CORE/src/novel_core/models/context.py`
- Modify: `CORE/src/novel_core/services/context_service.py`
- Modify: `CORE/src/novel_core/services/context_projection.py`
- Modify: `CORE/src/novel_core/repositories/context_repository.py`
- Modify: `CORE/tests/test_context_service.py`
- Modify: `CORE/tests/test_context_leakage.py` only if its expected context shape needs the renamed fields

**Interfaces:**
- Consumes: `DraftService.get_draft` parsed snapshots and E1 `render_context_html(document, max_visible_chars=4000)`.
- Produces: `RecentContext.previous_draft_context_html` and context metadata keys `previous_draft_context_visible_chars`, `previous_draft_context_blocks`, and `previous_draft_context`, with empty values when no previous draft exists.

- [ ] Write failing tests proving previous context is structured HTML with no IDs, notes, or annotations; retains type/scene/speaker/ruby; selects whole blocks from the end; includes a single oversized block whole; and reports visible-text counts rather than HTML length.
- [ ] Write failing tests proving no raw `body` access remains in ContextRepository/ContextService and that the same SQLite connection's DraftService is the sole stored-document parsing boundary.
- [ ] Run context tests and observe RED on legacy `previous_draft_tail`/`body` behavior.
- [ ] Replace the raw draft tail with the parsed latest document and `ContextProjectionResult`; update limits, returned counts, omitted counts, and truncation keys without changing unrelated bounded context behavior.
- [ ] Run all context, leakage, projection, and draft tests; commit structured context integration.

### Task 7: API draft contract, errors, and export

**Files:**
- Modify: `API/src/novel_api/schemas/authoring.py`
- Modify: `API/src/novel_api/routes/authoring.py`
- Modify: `API/src/novel_api/errors.py`
- Modify: `API/src/novel_api/service_container.py` only if a service wiring change is necessary
- Modify: `API/tests/test_phase3_api.py`, `API/tests/test_errors.py`, `API/tests/test_views.py`
- Create: `API/tests/test_phase_e_draft_api.py`

**Interfaces:**
- Consumes: Task 5 CORE service and DraftSnapshot/result types.
- Produces: DraftSave with nullable `plain_text`, `html`, `metadata_updates`, positive `restore_revision`, nullable positive expected parent, bounded source/summary; DraftRead formats `html`/`web`/`document`; repeated `annotation_keys`; `current_resource`; and `GET /api/v1/projects/{project_id}/episodes/{episode_id}/draft/export?format=narou`.

- [ ] Write failing API tests for `html`, `web`, and `document` GETs, notes/projection/query relevance, repeated annotation keys, empty string/null presence, metadata null-vs-omitted preservation, save response shape without full record, history metadata-only, absence convention, and Narou export filename/media type/content/warnings.
- [ ] Write failing API tests for `DOCUMENT_SCHEMA_ERROR` 422, semantic `VALIDATION_ERROR`, stale `VERSION_CONFLICT` 409 with authoring selected-emotions `current_resource`, and `DOCUMENT_STORAGE_ERROR` 500.
- [ ] Run focused API tests and confirm RED on the legacy body schema/route behavior.
- [ ] Implement presence-aware Pydantic conversion via `model_fields_set`/`exclude_unset`, preserve empty strings, reject irrelevant query arguments, use CORE projections/export directly, and map stored corruption explicitly without broad error-handler rewrites.
- [ ] Keep route-local project resolution/service opening behavior and existing non-Manuscript API contracts unchanged.
- [ ] Run focused API tests plus all existing API tests; commit API/error/export boundary.

### Task 8: MCP draft contract

**Files:**
- Modify: `MCP/src/novel_mcp/phase3_tools.py`
- Modify: `MCP/src/novel_mcp/phase3_tool_descriptions.py`
- Modify: `MCP/src/novel_mcp/api_client.py` only as needed for HTTPX-compatible repeated query values
- Modify: `MCP/tests/test_phase3_http_adapter.py`, `MCP/tests/test_phase3_mcp_tools.py`, `MCP/tests/test_http_adapter_e2e.py`

**Interfaces:**
- Consumes: Task 7 HTTP draft contract and existing `call_api`/error normalization.
- Produces: the same five Phase 3 tool names, with `episode_draft_get` format/projection/keys/include-notes, `episode_draft_save` structured fields, history, context, repeated query passthrough, and unchanged fail-closed `BACKEND_UNAVAILABLE` behavior.

- [ ] Write failing adapter tests proving `body` is absent, plain/html empty strings are forwarded, metadata/restore fields are exposed, revision-number restore is forwarded unchanged, GET format/projection/notes args map to query values, and multiple annotation keys use repeated parameters.
- [ ] Write failing tests asserting exact tool count 59, no removed/new names, and remote `DOCUMENT_STORAGE_ERROR`/`VERSION_CONFLICT` details remain intact.
- [ ] Run focused MCP tests and confirm RED against the legacy body-only signatures.
- [ ] Change only the existing phase3 draft handlers/descriptions and compatible query typing; keep MCP stateless and do not reimplement CORE semantics.
- [ ] Run focused MCP tests, the HTTP adapter E2E, repository boundary tests, and commit the MCP boundary.

### Task 9: Full backend regression, WEBUI non-Manuscript verification, and E2E classification

**Files:**
- Modify only tests/fixtures that expose the approved breaking draft contract: `CORE/tests/`, `API/tests/`, `MCP/tests/`, and existing test support as needed
- Do not modify: `WEBUI/frontend/src/**`, `WEBUI/frontend/e2e/manuscript.spec.ts`, or other E4/E5 implementation paths

**Interfaces:**
- Consumes: all Task 2–8 implementation boundaries.
- Produces: fresh verification evidence, a classified full Playwright result, and no Phase E Manuscript UI implementation.

- [ ] Run CORE `uv sync --all-groups`, Ruff, format check, Mypy, `pytest -W error`, coverage, and installed-wheel verification.
- [ ] Run API `uv sync --all-groups`, Ruff, format check, Mypy, `pytest -W error`, and coverage.
- [ ] Run MCP `uv sync --all-groups`, Ruff, format check, Mypy, `pytest -W error`, coverage, pre-commit, repository boundary checks, and exact 59-tool verification.
- [ ] Run WEBUI `npm ci`, lint, typecheck, unit tests, and build. These must pass without converting the Manuscript UI.
- [ ] Run the full current Playwright suite. If and only if `WEBUI/frontend/e2e/manuscript.spec.ts` fails solely because the removed `body` contract is still expected, record full E2E as FAIL with the exact assertion and classify it as the approved temporary E2 incompatibility; any other failure is a blocker and must be fixed within E2 or reported without advancing phases.
- [ ] Verify migration inventory is exactly 001–005, 001–004 blob SHAs are unchanged, `MCP/migrations` is absent, no compatibility shim/body persistence exists, no E4/E5 source changes exist, stable data remains untouched, and `git diff --check` is clean.

### Task 10: Scope audit, logical commits, and push

**Files:**
- Review all files changed from `618ad6b231c06302f910cef3a35fa416f52d6699` to `HEAD`; no new implementation files outside E2 scope.

**Interfaces:**
- Consumes: verified backend implementation and all recorded test outputs.
- Produces: a normal push of `codex/phase-e-integration` for ChatGPT review; no PR, merge, reset, force-push, Final Cutover, E3, E4, or E5.

- [ ] Run `git diff --name-only 618ad6b231c06302f910cef3a35fa416f52d6699...HEAD`, classify every path as E2-required, and remove only accidental agent-created unrelated changes; never touch stable user files.
- [ ] Ensure 3–6 logical commits exist with docs, migration/persistence, authoring, service/context/API, MCP, and verification boundaries as actually produced; never amend existing public commits.
- [ ] Re-run final targeted tests after the last code change and run `git status --short --branch`, `git diff --check`, migration SHA checks, and stable data/runtime path checks.
- [ ] Push normally with `git push origin codex/phase-e-integration`; do not force-push and do not create a PR.
- [ ] Inspect GitHub Actions for `core`, `api`, `mcp`, `invariants`, `webui`, and `webui-e2e`; report the exact run/job results and apply the E2E exception only as defined in Task 9.
- [ ] Final report must include stable/integration Git state, isolation/data-root evidence, spec/plan sync, migration/persistence contract, authoring/DraftService semantics, API/context/MCP contract, every verification result or exact unrun reason, E2E classification, `stable 2126 untouched`, `E3/E4/E5 not started`, `no PR/merge/force-push`, and `ChatGPT review pending`.
