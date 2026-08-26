# Novel MCP Phase 3 Implementation Plan

> Execution policy: ChatGPT owns architecture, design, and review. Codex Luna
> performs sequential implementation and verification. Subagent dispatch and
> model escalation are forbidden for this phase. Superpowers are limited to
> non-delegating TDD, verification, debugging, and documentation workflows.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add append-only episode drafts, bounded episode outline and context retrieval, leakage hardening, and the Phase 3 MCP tools with a real-writing acceptance gate.

**Architecture:** Build context as a service-owned read model from canonical repositories, applying episode, work, canon, disclosure, knowledge, and fixed-size boundaries before serialization. Drafts remain append-only and are never updated in place.

**Tech Stack:** Python 3.10+, official MCP Python SDK v2, standard-library `sqlite3`, explicit SQL migrations, pytest, and stdio transport.

**Spec:** `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`

## Global Constraints

- Keep all implementation, migration, and test paths under `MCP/`.
- Preserve the MCP tool/service/repository layering from Phases 1–2.
- Use the Python standard-library `sqlite3` module; no ORM or external context store.
- Start from `origin/main` at `0a10faf6b8c1ba9c838e6aea1cd0ab84cdb51ef6` on
  branch `codex/phase3-writing-context` in the dedicated isolated worktree.
- Do not modify the main checkout. Do not dispatch subagents or escalate the
  model. Follow this approved contract without an architecture redesign or
  silent simplification.
- Keep `MCP/migrations/001_initial.sql`, `002_search.sql`, and
  `003_narrative.sql` byte-for-byte unchanged. Add only `004_drafts.sql`; do
  not create `005_*` or later migrations.
- Keep `004_drafts.sql` immutable after it is applied.
- Draft saves append a new revision and never overwrite a prior revision.
- `episode_context` uses fixed bounds: 2 summaries, 4000 draft-tail characters, 30 world facts, 30 timeline events, and 50 information items.
- Exclude future episode data, future character states, future character knowledge, future reader disclosures, deprecated canon, and other-work data.
- Keep `reader_disclosures` separate from `character_knowledge_events`; a
  character knowing an item does not permit its protected statement to be
  returned before reader disclosure.
- Use explicit safe projections. Never return character `private_notes`,
  `profile_json`, or `death_date`, world-fact `details_json`, protected
  information `notes_json`, future episode title/summary, or draft history/body
  beyond the requested bounded tail.
- Return an authoring guard rather than protected future secret content.
- Never log draft bodies, tails, context secrets, or protected statements.
- `episode_context` is completely read-only: no INSERT, UPDATE, DELETE,
  CREATE, DROP, ALTER, migration, auto-reference, auto-summary, auto-canon,
  or draft save.
- Context candidates are limited to explicit current-episode references and
  effective participant knowledge; no vector search or whole-database semantic
  extraction is allowed.
- Current episode, scenes, participants, current reveal, and safe guards are
  critical output and are not silently removed by ordinary count bounds.
- Require the real-writing acceptance gate before treating Phase 3 output as writing-ready.
- Commit every task independently after its focused test suite passes.

## Final Contract Details

The implementation must preserve the following exact interfaces and evidence:

- Draft service: `save_draft(episode_id, body,
  expected_parent_draft_id=None, source_agent=None, change_summary="")`,
  `get_draft(episode_id, revision=None)`, and `history(episode_id, limit=20)`.
  `source_agent` is optional and bounded to 1..120 characters; change summaries
  are bounded to 1000 characters; history is bounded to 1..100 and excludes
  bodies.
- Draft hash is lower-case SHA-256 over exact UTF-8 body bytes. Draft table
  triggers reject raw UPDATE and DELETE. Saves use a write transaction that
  checks the current latest parent before allocating `MAX(revision)+1`.
- Outline and context use only safe participant, world-fact, and timeline
  projections. A deprecated target episode returns
  `DEPRECATED_CANON_FORBIDDEN`; cross-work and missing targets return
  structured `WORK_SCOPE_ERROR`/`NOT_FOUND` results.
- Information statements are returned only for reader disclosure positions
  before or equal to the target. Future/undisclosed related items become
  metadata-only safe guards with no statement, notes, future episode title, or
  future summary. The target episode's valid `foreshadowing_notes_json` is
  returned as a JSON array; malformed JSON is a structured error.
- `context_meta` includes `narrative_position`, all five fixed `limits`,
  `returned_counts`, `omitted_counts`, and `truncated` flags. It contains no
  secret text. Previous context follows narrative order, excludes deprecated
  episodes, and uses the prior episode's latest draft tail, not the target's
  prior revisions.
- The five Phase 3 tools must be registered exactly once, bringing the
  inventory to 23 + 27 + 5 = 55. There are no Phase 4 tools.
- `AcceptanceReport` records each required invariant independently, including
  migration sequence, draft append-only/CAS/hash, outline safety, context
  bounds/read-only, future/deprecated/cross-work/private-field leakage,
  guard presence, tool inventory, and `writing_ready`.

The repository must not receive `data/story.db` production content. Phase 3
tests use temporary qualification databases only.

### Task 0: Finalize Phase 3 documentation contract

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`
- Modify: `docs/superpowers/plans/2026-08-26-novel-mcp-phase3-plan.md`

Before production code, update the design status to Phase 1/2 merged and
Phase 3 approved, record the immutable migration boundary, secret modeling
rule, fixed context shape/bounds, exact five-tool surface, and deferred Phase
4 boundary. Self-review for stale Phase 3-deferred language, then commit:

```bash
git add docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md \
  docs/superpowers/plans/2026-08-26-novel-mcp-phase3-plan.md
git commit -m "docs: finalize Phase 3 writing contract"
```

### Task 1: Draft migration and append-only revisions

**Files:**
- Create: `MCP/migrations/004_drafts.sql`
- Create: `MCP/src/novel_mcp/repositories/draft_repository.py`
- Create: `MCP/src/novel_mcp/services/draft_service.py`
- Create: `MCP/tests/test_draft_service.py`

**Interfaces:**
- Consumes: episodes and database lifecycle from Phases 1–2.
- Produces: `save_draft(episode_id: int, body: str,
  expected_parent_draft_id: int | None = None, source_agent: str | None = None,
  change_summary: str = "") -> DraftRecord`, `get_draft(episode_id: int,
  revision: int | None = None) -> DraftRecord | None`, and
  `history(episode_id: int, limit: int = 20) -> tuple[DraftMetadata, ...]`.

- [ ] **Step 1: Write the failing test**

```python
def test_draft_save_is_append_only(service):
    episode = service.create_episode_for_test(27, "第二十七話")
    first = service.save_draft(episode.id, "revision one", source_agent="author")
    second = service.save_draft(
        episode.id, "revision two", expected_parent_draft_id=first.id,
        source_agent="author"
    )

    assert (first.revision, second.revision) == (1, 2)
    assert service.history(episode.id) == (first, second)
    assert service.get_latest_draft(episode.id) == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_draft_service.py -q`

Expected: FAIL because `004_drafts.sql` and draft services do not exist.

- [ ] **Step 3: Write minimal implementation**

Create the `drafts` table with episode scope, monotonic revision number, body,
metadata, SHA-256 hash, composite work/episode/parent integrity, and
append-only UPDATE/DELETE triggers. Allocate the next revision inside a
`BEGIN IMMEDIATE` transaction only after checking the latest parent and
`expected_parent_draft_id`; insert a new row and make history metadata-only.
Reject a missing or cross-work episode, invalid bounds, stale parents, and
empty/non-string bodies while preserving all prior bodies exactly.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_draft_service.py -q`

Expected: PASS, including exact body/hash preservation, concurrent revision
allocation through the SQLite transaction boundary, stale-parent rejection,
raw UPDATE/DELETE trigger rejection, bounded metadata history, empty-body
validation, and cross-work rejection.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_database_lifecycle.py MCP/tests/test_draft_service.py -q`; verify that migration 004 is applied after 003 and no update statement can change a draft body.

Expected: migration order is fixed and draft rows are append-only.

- [ ] **Step 6: Commit**

```bash
git add MCP/migrations/004_drafts.sql MCP/src/novel_mcp/repositories/draft_repository.py MCP/src/novel_mcp/services/draft_service.py MCP/tests/test_draft_service.py
git commit -m "feat: add append-only episode drafts"
```

### Task 2: Episode outline retrieval

**Files:**
- Create: `MCP/src/novel_mcp/repositories/outline_repository.py`
- Create: `MCP/src/novel_mcp/services/outline_service.py`
- Create: `MCP/tests/test_outline_service.py`

**Interfaces:**
- Consumes: chapter, episode, scene, participant, and reference services from Phase 2.
- Produces: `get_episode_outline(episode_id: int) -> EpisodeOutline`, containing
  the episode, ordered scenes, participant profiles, and referenced canonical
  entities without future context.

- [ ] **Step 1: Write the failing test**

```python
def test_episode_outline_returns_only_requested_episode(service):
    target = service.create_episode_for_test(10, "対象話")
    future = service.create_episode_for_test(11, "未来話")
    service.create_scene(target.id, "対象シーン")
    service.create_scene(future.id, "未来シーン")

    outline = service.get_episode_outline(target.id)

    assert [scene.summary for scene in outline.scenes] == ["対象シーン"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_outline_service.py -q`

Expected: FAIL because outline repository and service are absent.

- [ ] **Step 3: Write minimal implementation**

Assemble only the requested episode and its ordered scenes, participants, and
references. Resolve canonical status before including referenced entities and
return a structured not-found error for an absent or cross-work episode.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_outline_service.py -q`

Expected: PASS, including scene order, participant identity, reference
filtering, deprecated-canon exclusion, and future-episode exclusion.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_outline_service.py -q`; inspect the
outline service to confirm all reads are bounded by the requested episode and
configured work.

Expected: no query path can return a future episode as part of the outline.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/outline_repository.py MCP/src/novel_mcp/services/outline_service.py MCP/tests/test_outline_service.py
git commit -m "feat: add episode outline retrieval"
```

### Task 3: Episode Context Builder

**Files:**
- Create: `MCP/src/novel_mcp/repositories/context_repository.py`
- Create: `MCP/src/novel_mcp/services/context_service.py`
- Create: `MCP/src/novel_mcp/models/context.py`
- Create: `MCP/tests/test_context_service.py`

**Interfaces:**
- Consumes: effective character state, relationships, knowledge, disclosures,
  timeline, world facts, episode outline, and draft services from Phases 1–2
  and Tasks 1–2.
- Produces: `build_episode_context(episode_id: int) -> EpisodeContext`, with
  `episode`, `scenes`, `participants`, `world_facts`, `timeline_events`,
  `reader_context`, `protected_information_guards`, `recent_context`,
  `foreshadowing_notes`, and `context_meta` fields.

- [ ] **Step 1: Write the failing test**

```python
def test_context_applies_fixed_bounds_and_effective_state(service):
    episode = service.create_episode_for_test(20, "第二十話")
    seed_context_rows(service, world_fact_count=40, timeline_count=40)
    context = service.build_episode_context(episode.id)

    assert len(context.world_facts) == 30
    assert len(context.timeline_events) == 30
    assert context.context_meta["previous_episode_summaries"] == 2
    assert context.context_meta["previous_draft_tail_chars"] == 4000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_context_service.py -q`

Expected: FAIL because the context model and builder do not exist.

- [ ] **Step 3: Write minimal implementation**

Build a read-only structured result using the fixed bounds from the design
specification. Resolve character state, relationships, and knowledge at the
requested episode. Fetch at most two previous summaries, trim the previous
draft tail to 4000 characters, and include deterministic ordering metadata.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_context_service.py -q`

Expected: PASS, including all five bounds, participant effective state,
reader context, recent context, stable ordering, and no mutation during reads.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_context_service.py -q`; use a connection
trace callback in the test to assert that the builder performs no INSERT,
UPDATE, DELETE, or migration statement.

Expected: context assembly is fully read-only.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/context_repository.py MCP/src/novel_mcp/services/context_service.py MCP/src/novel_mcp/models/context.py MCP/tests/test_context_service.py
git commit -m "feat: build bounded episode context"
```

### Task 4: Future-information and deprecated-canon leakage hardening

**Files:**
- Modify: `MCP/src/novel_mcp/services/context_service.py`
- Create: `MCP/src/novel_mcp/services/context_guards.py`
- Create: `MCP/tests/test_context_leakage.py`

**Interfaces:**
- Consumes: `EpisodeContext`, canonical-status checks, episode ordering, and
  disclosure/knowledge timelines from Task 3.
- Produces: `check_context_guards(episode_id: int) -> tuple[ContextGuard, ...]`
  and a context result that contains guard metadata without protected secret
  bodies.

- [ ] **Step 1: Write the failing test**

```python
def test_context_returns_authoring_guard_without_future_secret_body(service):
    item = service.create_information("国家AIの秘密の本文", "true")
    future_episode = service.create_episode_for_test(37, "未来話")
    service.set_reader_disclosure(item.id, future_episode.id)
    target = service.create_episode_for_test(24, "対象話")

    context = service.build_episode_context(target.id)

    assert context.protected_information_guards
    assert "国家AIの秘密の本文" not in context.to_json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_context_leakage.py -q`

Expected: FAIL because future-data and deprecated-canon guards are not enforced.

- [ ] **Step 3: Write minimal implementation**

Run guard checks before serializing context. Exclude future state, future
knowledge, future reader disclosures, and deprecated canon. For a future item
that is relevant to authoring, return only a typed guard with safe metadata such
as the affected entity and reveal boundary. Never put the protected statement
body in the guard.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_context_leakage.py -q`

Expected: PASS, including future disclosure, future character knowledge,
future character state, deprecated canon, and cross-work leakage cases.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_context_service.py MCP/tests/test_context_leakage.py -q`; scan serialized context fixtures for the protected source statements.

Expected: only safe guard descriptions appear, and no future secret text is
returned.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/services/context_service.py MCP/src/novel_mcp/services/context_guards.py MCP/tests/test_context_leakage.py
git commit -m "feat: harden episode context boundaries"
```

### Task 5: Phase 3 MCP tools and real-writing acceptance gate

**Files:**
- Modify: `MCP/src/novel_mcp/mcp_server.py`
- Create: `MCP/src/novel_mcp/phase3_tools.py`
- Create: `MCP/tests/test_phase3_mcp_tools.py`
- Create: `MCP/tests/test_phase3_acceptance.py`

**Interfaces:**
- Consumes: outline, context, and draft services from Tasks 1–4.
- Produces: `episode_outline_get`, `episode_context`, `episode_draft_get`,
  `episode_draft_save`, and `episode_draft_history` registrations, plus
  `run_phase3_acceptance(database) -> AcceptanceReport`.

- [ ] **Step 1: Write the failing test**

```python
def test_phase3_acceptance_requires_context_guards_and_append_only_drafts(server):
    report = run_phase3_acceptance(server.database)

    assert report.context_is_bounded is True
    assert report.future_leakage_is_blocked is True
    assert report.drafts_are_append_only is True
    assert report.writing_ready is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_phase3_mcp_tools.py MCP/tests/test_phase3_acceptance.py -q`

Expected: FAIL because Phase 3 adapters and the acceptance gate are absent.

- [ ] **Step 3: Write minimal implementation**

Register exactly the five Phase 3 tools, delegate to services, serialize
structured context and guards, and expose draft history without an update or
delete operation. The acceptance gate must exercise fixed bounds, all leakage
categories, deprecated-canon exclusion, configured-work scope, and two draft
saves that produce revisions 1 and 2. A positive process exit alone is not a
passing gate; each assertion must be recorded in `AcceptanceReport`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_phase3_mcp_tools.py MCP/tests/test_phase3_acceptance.py -q`

Expected: PASS, including tool registration, safe context serialization,
append-only draft operations, and all acceptance-gate assertions.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests -q`; inspect `server.tool_names()` and confirm
that all Phase 1–3 names are present exactly once, no database file is created
under the repository root, and the acceptance report lists every guard.

Expected: the complete test suite passes and the real-writing gate is backed by
specific evidence rather than a wrapper exit code.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/mcp_server.py MCP/src/novel_mcp/phase3_tools.py MCP/tests/test_phase3_mcp_tools.py MCP/tests/test_phase3_acceptance.py
git commit -m "feat: expose Phase 3 authoring tools"
```
