# Fiction Style Analysis SA-F Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the SA-F ReviewItem, append-only ManualOverride, InferenceReview, Effective View, status, and correction/recompute contracts without changing the database schema or implementing SA-G/H behavior.

**Architecture:** Keep Review/Override persistence and validation in CORE services, expose the explicit SA-F operations through the existing API service container and style-analysis router, and make read-side effective output/status use the existing CurrentRunResolver and typed resolvers. Metric-only correction enqueues the existing internal `metrics` preset; resolver/registry corrections only change fingerprints and report semantic stale state.

**Tech Stack:** Python 3.10+, SQLite migrations 006-008 as-is, FastAPI/Pydantic v2, pytest, ruff, mypy.

**Spec:** `docs/features/fiction-style-analysis/detailed-design/04-entity-and-speaker.md`, `05-term-analysis.md`, `06-scene-semantics.md`, `07-style-metrics.md`, `09-analysis-runtime.md`, `10-review-and-overrides.md`, `12-storage-schema.md`, `13-api-and-webui.md`, `14-testing-and-evaluation.md`.

## Global Constraints

- Preserve migrations 001-008 byte-for-byte; add no table, endpoint family outside SA-F, or new analyzer/metric.
- ManualOverride is append-only with `set|clear|revert`; never update/delete an existing event or add an active unique pointer.
- ReviewItem and InferenceReview remain separate responsibilities; ReviewItem close operations never perform domain corrections.
- Use the exact ReviewItem subject registry and InferenceReview field-path registry from `10-review-and-overrides.md`.
- Resolve scopes from subjects; Project Entity/Term uses `document_id`, Reference Entity/Term uses `reference_work_id`, and structure subjects use their owning document.
- Use Current Text/Structure/Run lineage explicitly; never infer Current from latest historical rows.
- Do not auto-enqueue full analysis for human corrections; only the four metric-only field groups may use internal `metrics` recompute.
- Preserve user-owned untracked files and the existing review branch; do not merge, rebase, force-push, tag, release, or deploy.

---

### Task 1: CORE review models, scope validation, and append-only persistence

**Files:**
- Create: `CORE/src/novel_core/style_analysis/review_models.py`
- Create: `CORE/src/novel_core/style_analysis/review_service.py`
- Test: `CORE/tests/test_style_analysis_reviews.py`

**Interfaces:**
- `ReviewItemRecord`, `ManualOverrideRecord`, and `InferenceReviewRecord` expose the persisted fields from migration 007/008.
- `ReviewService.create_manual_review_item(...)`, `.resolve_review_item(...)`, `.ignore_review_item(...)`, `.create_override(...)`, and `.create_inference_review(...)` validate subject scope, field registry, value schema, run/structure lineage, and return records.
- `ReviewService.list_*` and `.get_*` provide deterministic read methods used by the API catalog.

- [ ] **Step 1: Write failing tests** for ReviewItem create/defaults/scope, expected-version resolve/ignore, closed-item rejection, append-only override set/clear/revert, active-revert rejection, and all InferenceReview registry/lineage checks.
- [ ] **Step 2: Run `uv run pytest -q tests/test_style_analysis_reviews.py`** and confirm the new tests fail because the service and models do not exist.
- [ ] **Step 3: Implement the two dataclasses and one service using one transaction per mutation, exact SQLite scope columns, canonical JSON serialization, and `created_at`/`version` rules from the schema.
- [ ] **Step 4: Run the focused tests and confirm they pass without changing migrations.
- [ ] **Step 5: Commit `feat(style-analysis): add review and override persistence` after diff and migration checks.

### Task 2: Effective resolvers, effective output, and derived analysis status

**Files:**
- Modify: `CORE/src/novel_core/style_analysis/semantic_metric_support.py`
- Modify: `API/src/novel_api/style_analysis/catalog_effective.py`
- Modify: `API/src/novel_api/style_analysis/catalog_current.py`
- Modify: `API/src/novel_api/style_analysis/catalog_service.py`
- Test: `CORE/tests/test_style_analysis_effective_views.py`
- Test: `API/tests/test_style_analysis_review_status.py`

**Interfaces:**
- Add typed read-side resolvers for entity enabled/name/type, term enabled/label/type, and scene effective axes while retaining existing resolver return contracts.
- `effective_outputs(...)` applies Manual > Confirmed Current > Current Eligible > Unknown/Default and exposes raw/effective values without mutating annotations.
- `StyleAnalysisCatalogService.analysis_status(...)` reports independent `basic` and `semantic` states and reasons using CurrentRunResolver fingerprints.

- [ ] **Step 1: Write failing tests** for Manual > Confirmed > Inferred, rejected inference, explicit clear/revert semantics, stale structure-dependent overrides, effective scene axes, deterministic-only status, human-state stale precedence, and current historical-run reuse.
- [ ] **Step 2: Run the focused CORE/API tests and confirm failures identify missing effective behavior rather than fixture errors.
- [ ] **Step 3: Implement only the typed read-side helpers and catalog/status integration, reusing the existing CurrentRunResolver and policy inputs.
- [ ] **Step 4: Run the focused tests and then the existing semantic/runtime/catalog tests.
- [ ] **Step 5: Commit `feat(style-analysis): derive effective views and analysis status`.

### Task 3: SA-F API contracts and mutation routes

**Files:**
- Modify: `API/src/novel_api/schemas/style_analysis.py`
- Modify: `API/src/novel_api/style_analysis/catalog_service.py`
- Modify: `API/src/novel_api/routes/style_analysis.py`
- Modify: `API/src/novel_api/style_analysis/job_service.py` only if the existing internal metrics enqueue needs a narrow adapter.
- Test: `API/tests/test_style_analysis_review_api.py`

**Interfaces:**
- Add the exact request/response models for `POST /overrides`, `POST /inference-reviews`, `GET /review-items`, `GET /review-items/{id}`, `POST /review-items`, `POST /review-items/{id}/resolve`, and `POST /review-items/{id}/ignore`.
- Return 201/200 as specified, map domain failures to stable 400/404/409/422 error codes, and never expose generic review confirm/reject endpoints.
- For metric-only correction, create the existing internal `metrics` job payload only after the append-only event commits; for registry/resolution changes, leave automatic full analysis unscheduled.

- [ ] **Step 1: Write failing API tests** for exact schemas, scope errors, field errors, ReviewItem lifecycle, append-only semantics, response envelopes, and metric-only versus semantic-reanalysis classification.
- [ ] **Step 2: Run `uv run pytest -q tests/test_style_analysis_review_api.py`** and confirm the endpoints are absent or return the expected pre-implementation failures.
- [ ] **Step 3: Implement schemas, catalog forwarding methods, routes, and narrow error mapping using existing project connection helpers.
- [ ] **Step 4: Run focused API tests and the full API suite with `-W error`.
- [ ] **Step 5: Commit `feat(api): expose style review and override operations`.

### Task 4: SA-F verification, review, and delivery

**Files:**
- Modify only files already listed in Tasks 1-3 if verification exposes an SA-F defect.
- Test: existing CORE/API tests plus `CORE/tests/test_style_analysis_reviews.py`, `CORE/tests/test_style_analysis_effective_views.py`, and `API/tests/test_style_analysis_review_api.py`.

- [ ] **Step 1: Run CORE `uv run pytest -W error -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `python -m compileall src`.
- [ ] **Step 2: Run API `uv run pytest -W error -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `python -m compileall src`.
- [ ] **Step 3: Verify `git diff --check`, migration checksums, changed-file scope, and the existing untracked user files remain untouched.
- [ ] **Step 4: Commit/push the final SA-F changes on `codex/fiction-style-analysis-sa-a-prep`.
- [ ] **Step 5: Submit the exact pushed HEAD to the SA-F ChatGPT thread for review, wait up to 20 minutes, and resolve any BLOCKER/MAJOR with a new test-first cycle before moving to SA-G.

## Self-Review Checklist

- Scope coverage: Tasks 1-3 cover ReviewItem, Override, InferenceReview, typed Effective View, status, API, and metric-only recompute; Task 4 covers all required verification and review.
- No migration or schema task is present because SA-F explicitly consumes existing 007/008 tables.
- No SA-G lint, SA-H WebUI, new analyzer, or full-analysis auto-queue task is present.
- All mutations have a failing test step before production implementation and all public routes have exact request/response tests.
