# Novel MCP Phase 1 PR #1 Review Fixes Implementation Plan

> Execution policy: ChatGPT owns architecture, design, and review. Codex Luna
> performs sequential implementation and verification. Subagent dispatch or
> model escalation occurs only when the user explicitly requests it.
> Superpowers are limited to non-delegating TDD, verification, debugging, and
> documentation workflows. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Align the unmerged Phase 1 MCP implementation with the approved normalized core data model, exact-date-independent timeline model, SQLite invariants, bounded trigram-first Japanese search, canon transition/noise policy, and descriptive MCP schemas without entering Phase 2 or Phase 3.

**Architecture:** Correct the pre-merge Phase 1 migrations in place, then keep all normalized row mapping and SQL in repositories, validation/policy/transactions in services, and thin structured MCP handlers. Use compatibility properties and input aliases only where they do not weaken the normalized schema or make free text the participant source of truth.

**Tech Stack:** Python 3.10+, concrete Python 3.13 development runtime, uv, stdlib sqlite3, official MCP Python SDK v2, pydantic field metadata through MCP function schemas, pytest/pytest-cov, Ruff, strict mypy, pre-commit, and stdio transport.

**Spec:** `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`

## Execution status

- [x] Tasks 1-6 implemented and covered by focused/full tests.
- [x] Phase 1 schema, services, search, Canon policy, MCP descriptions, and
  JSON Schema bounds are aligned with the approved Design Specification.
- [x] Phase 2/3 work was not started.

## Global Constraints

- Keep exactly the existing 23 Phase 1 tools; add no Phase 2/3 tools, tables, migrations, web code, ORM, or story database.
- Treat the Design Specification as authoritative; update the existing Phase 1 plan to match the normalized fields rather than simplifying the design to fit the old adapter.
- Because PR #1 is unmerged and no production story database exists, correct `001_initial.sql` and `002_search.sql` in place, update checksum fixtures, and document this as a pre-merge correction. Preserve future `003_narrative.sql` and `004_drafts.sql` responsibilities.
- Preserve MCP → Service → Repository → SQLite layering. MCP and services contain no SQL tokens; repositories own SQL and database-specific behavior.
- Keep work scoping, foreign keys, `canon_status` checks, entity-type checks, version checks, optimistic locking, structured errors, and source-size limits.
- Normal content edits in `idea`/`draft` do not create `canon_decisions`; canonical transitions, canonical content edits, deprecated transitions, and explicit authorial decisions do.
- Search prefers an available FTS5 trigram strategy and otherwise uses parameterized, escaped `LIKE`; strategy remains diagnostically observable and derived indexes are rebuildable from canonical rows.

### Task 1: Normalize the Phase 1 schema and documentation

**Files:**
- Modify: `MCP/migrations/001_initial.sql`
- Modify: `MCP/migrations/002_search.sql`
- Modify: `MCP/tests/test_database_lifecycle.py`
- Modify: `MCP/tests/test_development_foundation.py`
- Modify: `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`
- Modify: `docs/superpowers/plans/2026-08-26-novel-mcp-phase1-plan.md`

**Schema contract:**
- `world_facts`: `topic_key`, `category`, `title`, `statement`, `details_json`, nullable `valid_from`/`valid_to`, checked `canon_status`, nonnegative `importance`, and `version >= 1` in addition to identity/work/timestamps.
- `works`: normalized `working_title`, `genre`, `premise`, valid-JSON
  `themes_json`, `description`, constrained `production_status`, `slug`,
  version, and timestamps.
- `world_facts.topic_key` is indexed but intentionally non-unique within a
  work so validity ranges can coexist.
- `characters`: `character_key`, checked `entity_type` in `human|ai|organization`, normalized descriptive/profile fields, checked `canon_status`, and `version >= 1`.
- `timeline_events`: nullable internal range endpoints `time_start`/`time_end`, checked `date_precision` in `unknown|year|season|month|day`, human `date_display`, normalized description/category/location/cause/consequence fields, checked status, importance, and version.
- `timeline_event_participants`: `event_id`/`timeline_event_id` and `character_id` foreign keys plus `role`; no participant label column.
- `relationships`: source/target character foreign keys, `relationship_type`, `description`, checked status, and version.
- Add SQLite checks and foreign keys for work, location, event participants, relationship endpoints, canon statuses, entity types, and positive versions. Service checks remain required for cross-work operations.

- [ ] **Step 1: Write failing schema/contract tests**

Add tests that inspect the normalized column inventories and constraints via `PRAGMA table_info`, `PRAGMA foreign_key_list`, and invalid insert attempts. Assert migrations apply once, changed pre-merge checksums are recorded, and no `003_narrative.sql` or `004_drafts.sql` is created.

- [ ] **Step 2: Run the schema tests and observe the old adapter fail**

Run: `uv run pytest tests/test_database_lifecycle.py tests/test_development_foundation.py -q`

Expected: FAIL because the current schema still uses `fact_key/body`, `summary`, `chronology_sort_key`, and `participant_label` and lacks the required checks.

- [ ] **Step 3: Implement the pre-merge migration correction**

Rewrite only the unmerged `001_initial.sql` core tables and update `002_search.sql` indexes for normalized canonical columns. Keep `schema_migrations` checksum enforcement intact. Do not create future migration files.

- [ ] **Step 4: Verify schema tests and documentation consistency**

Run the focused tests and search the design/plan for every normalized field and explicit pre-merge correction note. Verify old future migration responsibilities remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add MCP/migrations/001_initial.sql MCP/migrations/002_search.sql MCP/tests/test_database_lifecycle.py MCP/tests/test_development_foundation.py docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md docs/superpowers/plans/2026-08-26-novel-mcp-phase1-plan.md
git commit -m "feat: align Phase 1 schema with approved data model"
```

### Task 2: Normalize world facts, characters, relationships, and repository records

**Files:**
- Modify: `MCP/src/novel_mcp/repositories/world_fact_repository.py`
- Modify: `MCP/src/novel_mcp/repositories/character_repository.py`
- Modify: `MCP/src/novel_mcp/repositories/relationship_repository.py`
- Modify: `MCP/src/novel_mcp/services/world_fact_service.py`
- Modify: `MCP/src/novel_mcp/services/character_service.py`
- Modify: `MCP/src/novel_mcp/services/relationship_service.py`
- Modify: corresponding service tests

**Interfaces:** repositories return full normalized records. Services accept normalized create/update fields, retain narrow compatibility aliases only as Python properties, validate entity types/details/importance/date values, and pass canonical content updates through the shared canon mutation path. Relationship and character endpoints remain configured-work scoped.

- [ ] **Step 1: Add failing normalized record/service tests**

Test full field persistence and round trips, `entity_type` rejection, `importance` bounds, `details_json` validity, normalized relationship description, canonical mirror consistency, and that ordinary draft edits do not create canon decision rows.

- [ ] **Step 2: Run focused tests and observe failure**

Run: `uv run pytest tests/test_world_fact_service.py tests/test_character_service.py tests/test_relationship_service.py -q`

Expected: FAIL against the old six-field records and old column names.

- [ ] **Step 3: Implement repository/service normalization**

Map every normalized column explicitly, keep SQL in repositories, use repository-owned transaction helpers, preserve typed not-found/work-scope errors, and avoid making `participant_label` or legacy aliases canonical.

- [ ] **Step 4: Run focused tests and full service regression tests**

Run the three focused modules, then `uv run pytest tests -q`.

- [ ] **Step 5: Commit**

```bash
git add MCP/src/novel_mcp/repositories MCP/src/novel_mcp/services MCP/tests/test_world_fact_service.py MCP/tests/test_character_service.py MCP/tests/test_relationship_service.py
git commit -m "feat: normalize Phase 1 world and character records"
```

### Task 3: Add non-exact timeline ranges and character-backed participants

**Files:**
- Modify: `MCP/src/novel_mcp/repositories/timeline_repository.py`
- Modify: `MCP/src/novel_mcp/services/timeline_service.py`
- Modify: `MCP/tests/test_timeline_service.py`

**Interfaces:** `create_event`/`update_event` accept `time_start`, `time_end`, `date_precision`, and `date_display` plus normalized event fields. The existing exact-day `event_date`/`new_date` call shape remains a narrow adapter that produces `date_precision=day`. Participants are `(character_id, role)` pairs and are returned as typed participant records. Range queries use overlap of internal endpoints, while `date_display` is never used as a sort key.

- [ ] **Step 1: Add failing date/participant tests**

Cover year, season, month, day, and unknown-display inputs; inclusive overlap range behavior; invalid endpoint ordering; location foreign keys; participant character IDs/roles; and rejection of a participant from another work.

- [ ] **Step 2: Run focused tests and observe failure**

Run: `uv run pytest tests/test_timeline_service.py -q`

Expected: FAIL because the current schema requires an exact `chronology_sort_key` and stores free-text participant labels.

- [ ] **Step 3: Implement normalized timeline storage and service parsing**

Parse supported display forms (`YYYY年`, `YYYY年春頃`, `YYYY年M月頃`, exact ISO day, and `正確な日付不明`) into internal inclusive endpoints; retain explicit `date_display`; validate location and participant work scope before transaction; keep event update CAS and missing-row `NOT_FOUND` classification.

- [ ] **Step 4: Run focused and full tests**

Run `uv run pytest tests/test_timeline_service.py -q` and then the full suite.

- [ ] **Step 5: Commit**

```bash
git add MCP/src/novel_mcp/repositories/timeline_repository.py MCP/src/novel_mcp/services/timeline_service.py MCP/tests/test_timeline_service.py
git commit -m "feat: support normalized non-exact timeline dates"
```

### Task 4: Implement trigram-first Japanese search with diagnostics

**Files:**
- Modify: `MCP/src/novel_mcp/repositories/search_repository.py`
- Modify: `MCP/src/novel_mcp/services/search_service.py`
- Modify: `MCP/tests/test_japanese_search.py`

- [ ] **Step 1: Add failing search strategy tests**

Cover detected FTS5 trigram, forced fallback, Japanese substring, literal `%`/`_`, configured work scope, deterministic ID ordering, and limit 100.

- [ ] **Step 2: Run tests and observe current always-LIKE behavior**

Run: `uv run pytest tests/test_japanese_search.py -q`

Expected: FAIL because diagnostics report `parameterized_like` and the repository never attempts FTS5 trigram.

- [ ] **Step 3: Implement strategy selection**

Probe FTS5 trigram capability once per repository, use an ephemeral/rebuildable FTS5 trigram index for canonical rows when available, and fall back to parameterized escaped `LIKE` when unavailable or when a trigram query cannot be represented. Return the selected strategy in `SearchDiagnostic`; never treat FTS/index rows as canonical.

- [ ] **Step 4: Run focused and full tests**

Run focused search tests and the full suite; assert the strategy diagnostic for both paths.

- [ ] **Step 5: Commit**

```bash
git add MCP/src/novel_mcp/repositories/search_repository.py MCP/src/novel_mcp/services/search_service.py MCP/tests/test_japanese_search.py
git commit -m "feat: prefer SQLite trigram search with fallback"
```

### Task 5: Complete canon transition matrix and remove draft decision noise

**Files:**
- Modify: `MCP/src/novel_mcp/services/canon_service.py`
- Modify: `MCP/src/novel_mcp/repositories/canon_repository.py`
- Modify: `MCP/tests/test_canon_service.py`

- [ ] **Step 1: Add failing transition/noise tests**

Assert `deprecated -> canon` is rejected, `deprecated -> draft` succeeds, `draft -> canon` requires a reason, `canon -> deprecated` requires a reason, stale status updates return `VERSION_CONFLICT`, and draft/idea ordinary content edits leave `canon_decisions` unchanged.

- [ ] **Step 2: Run focused tests and observe failure**

Run: `uv run pytest tests/test_canon_service.py -q`

Expected: FAIL because the current matrix derives policy only from the target and records ordinary edits as `ordinary authoring edit` decisions.

- [ ] **Step 3: Implement the explicit matrix and audit policy**

Use an explicit allowed-transition mapping; keep decision/change insertion atomic for canonical transitions/content edits/explicit decisions; return no decision for ordinary idea/draft edits; preserve canonical reason requirements and normalized mirror fields.

- [ ] **Step 4: Run canon tests and full suite**

Run `uv run pytest tests/test_canon_service.py -q` and then `uv run pytest tests -q`.

- [ ] **Step 5: Commit**

```bash
git add MCP/src/novel_mcp/services/canon_service.py MCP/src/novel_mcp/repositories/canon_repository.py MCP/tests/test_canon_service.py
git commit -m "fix: enforce Phase 1 canon transition policy"
```

### Task 6: Expand all 23 MCP schemas and descriptions

**Files:**
- Modify: `MCP/src/novel_mcp/mcp_server.py`
- Create: `MCP/src/novel_mcp/tool_descriptions.py`
- Modify: `MCP/tests/test_phase1_mcp_tools.py`
- Modify: `MCP/tests/test_phase1_acceptance.py`

Register exactly the existing 23 names with explicit `Use this when ...` descriptions. Use `typing.Literal` for canon status, entity type, and date precision, and pydantic `Field(ge=0, le=100)` for limits plus bounded text fields so tools/list exposes JSON Schema constraints. Handlers remain SQL-free and delegate normalized inputs to services.

- [ ] **Step 1: Add failing tools/list tests**

Assert every tool has a non-empty `Use this when` description, every tool has explicit annotations, limit schema has maximum 100, and enum fields expose their allowed values. Add normalized create/update/get/search structured-output tests.

- [ ] **Step 2: Run focused MCP tests and observe failure**

Run: `uv run pytest tests/test_phase1_mcp_tools.py tests/test_phase1_acceptance.py -q`

- [ ] **Step 3: Implement descriptions and normalized handler signatures**

Keep the exact 23-name inventory and structured error behavior; split only the description/metadata mapping if needed to preserve the source-size gate.

- [ ] **Step 4: Run full MCP and stdio smoke tests**

Run the full suite and an isolated `run_stdio_async` smoke with a temporary database outside the repository.

- [ ] **Step 5: Commit**

```bash
git add MCP/src/novel_mcp/mcp_server.py MCP/src/novel_mcp/tool_descriptions.py MCP/tests/test_phase1_mcp_tools.py MCP/tests/test_phase1_acceptance.py
git commit -m "feat: describe and normalize Phase 1 MCP tools"
```

### Task 7: Final verification and CI reconciliation

- [ ] Run from `MCP`: `uv sync --all-groups`, Ruff check, Ruff format check, strict mypy, pytest, coverage pytest, and `uv run pre-commit run --all-files`.
- [ ] Run from repository root: `python MCP/scripts/check_source_size.py`, `git diff --check`, `git status`, and the isolated stdio smoke.
- [ ] Verify PR #1 push and both push/pull-request GitHub Actions checks on the new HEAD.
- [ ] Confirm no Phase 2/3 files/tools, no production story.db, and no tracked reports.
