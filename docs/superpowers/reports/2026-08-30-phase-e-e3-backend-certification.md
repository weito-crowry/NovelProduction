# NovelProduction Phase E — E3 Backend Certification

## Result

**PASS — Fresh Rerun #4**

- Certification time: 2026-08-30 19:27:15–19:32:55 JST (UTC stage timestamps in the evidence)
- Repository: `weito-crowry/NovelProduction`
- Worktree: `C:\Users\weito\Documents\src\NovelProduction-phase-e-integration`
- Branch: `codex/phase-e-integration`
- Certified HEAD at start and end: `4089b10669d068c2eb74dbe0ab384b1c40ef7fbc`
- Fresh certification root: `C:\Users\weito\Documents\src\NovelProduction-phase-e-integration\.tmp\phase-e-e3-20260830-192607-435-r4`
- API: `http://127.0.0.1:18765`
- Stable runtime `127.0.0.1:8765` and stable DB were not contacted. Stable process/listener inspection was OS-only.
- Harness-only correction count: **2**. No source, test, spec, migration, product, or stable-runtime changes were made.

The complete machine-readable evidence is in:

`C:\Users\weito\Documents\src\NovelProduction-phase-e-integration\.tmp\phase-e-e3-20260830-192607-435-r4\certification-evidence.json`

## Process history

The earlier #2/#3 outcomes are retained as process history and are not product defects:

1. Initial `ExceptionGroup` result was inconclusive; canonical probes subsequently passed.
2. The tool-count expectation was a temporary harness metric-definition defect.
3. Fresh Rerun #2 had a stale temporary `project_scoped` harness variable.
4. Fresh Rerun #3 used the wrong temporary extraction for `episode_draft_get(format=document)`.

Fresh Rerun #4 applied the authorized second harness-only correction. All `episode_draft_get` formats were treated as `DraftRead`; the canonical/html/web value was read from `DraftRead["content"]`. Revision 3 compared `revision3_document["content"]` with `revision1_document["content"]`. The harness also recorded compact response-shape summaries for the major response types.

## Certification inventory

- API readiness: health `ok`, API version `v1`; project list initially empty.
- MCP stdio: official `stdio_client` and `ClientSession` used; initialize and `list_tools` passed.
- MCP tools: 59 total; 4 project-management tools; 55 existing project-data tools.
- Existing project-data tools requiring `project_id`: `55/55`.
- All tools requiring `project_id`: `57/59`.
- `project_list` and `project_create` do not require `project_id`; `project_get` and `project_update` do.
- `project_select`: false; export MCP tool absent.
- `episode_draft_save` and `episode_draft_get` schemas were captured in the evidence.

## Project, database, and fixtures

- Project: `project-20260830-102813`.
- Database: `...\.tmp\phase-e-e3-20260830-192607-435-r4\project-20260830-102813\story.db`.
- Migrations: `001_initial.sql`, `002_search.sql`, `003_narrative.sql`, `004_drafts.sql`, `005_structured_drafts.sql`.
- `drafts` columns: `id`, `work_id`, `episode_id`, `revision`, `parent_draft_id`, `document_json`, `source_agent`, `change_summary`, `created_at`.
- Draft uniqueness: `(episode_id, revision)`, `(work_id, episode_id, id)`, `(work_id, id)`.
- Draft foreign keys and append-only update/delete triggers were present.
- SQLite integrity: `ok`; foreign-key check rows: `0`.
- Core read-only database open: `PASS`; `foreign_keys=1`.
- Fixture IDs: work `1`, chapter `1`, episode1 `1`, episode2 `2`, scene `1`, character `1`.
- Episode ordering and common chapter constraints passed; episode2 had no draft before certification.

## Draft certification

- Revision 1: draft ID `1`; no parent; empty `id_map`.
- Revision 2: draft ID `2`; parent `1`.
- Revision 3 restore: draft ID `3`; parent `2`; content restored from Revision 1.
- `id_map`: `new-dialogue-1` → `blk_f263d83ff4144cc59fae720240d80cdd`; `note-fixture-1` → `blk_3bd815e6a1384b0c88f34607fd235d9c`.
- Structured annotation and scene/speaker metadata passed, including emotions `tense`, `hopeful` and the complex custom annotation.
- Authoring, WEB default, and WEB-with-notes projections passed with the expected formal IDs, notes, and metadata visibility.
- Invalid live reference returned `VALIDATION_ERROR` with no write.
- Stale CAS returned `VERSION_CONFLICT` with no append; current resource metadata was reported.
- Episode context returned the expected previous-draft context and bounded metadata.
- History revisions were exactly `[1, 2, 3]`, with no manuscript content leakage and the expected parent chain.
- Narou export passed: format `narou`, media type `text/plain`, filename `episode-1-r2.txt`, warnings `[]`.

## Response-shape evidence

The evidence recorded 13 compact summaries. In particular:

- Revision 1/2/3 document reads: top-level `DraftRead` keys include `format` and `content`; `content` is an object with `blocks`, `schema_version`, and `type`.
- Revision 1 HTML and Revision 2 HTML: `content` is a string.
- Revision 2 WEB and WEB-with-notes: `content` is a string.
- Context: object with `context_meta`, `episode`, `recent_context`, scenes, participants, and related context keys.
- History: list of 3 objects.
- Narou export: envelope keys `data`, `project_id`; data keys include `content`, `format`, `media_type`, `suggested_filename`, and `warnings`.

## Fail-closed and cleanup

- API was stopped by the harness; listener on port `18765` was absent afterward (only normal TCP `TIME_WAIT` was observed).
- The MCP backend-unavailable probe returned `BACKEND_UNAVAILABLE` with message `NovelProduction API is unavailable.` and no fallback success.
- MCP stderr was captured at `...\mcp.stderr.log` (3,453 bytes); it contains the expected isolated API request statuses, including the deliberate `400` and `409` negative cases.
- Official stdio cleanup was used; no custom MCP subprocess wrapper or custom task group was used.
- Stable port `8765` remained under its existing process and was not stopped or queried.

## Git, Actions, and handoff

- This report is the only tracked deliverable from the certification; `.tmp` remains local evidence only.
- Required Actions checks: `core`, `api`, `mcp`, `invariants`, `webui`.
- The only pre-authorized legacy exception is the known `webui-e2e/manuscript.spec.ts` body-contract failure. Any other required-check failure blocks certification follow-up.
- E4/E5 were not started by this E3 certification.
- Stable port `2126` was not contacted.
- Review remains required before any merge or next phase advancement.
