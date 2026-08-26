# Novel MCP Phase 2 Implementation Plan

> Execution policy: ChatGPT owns architecture, design, and review. Codex Luna
> performs sequential implementation and verification. This repository
> explicitly forbids subagent dispatch and model escalation for this phase.
> Superpowers are limited to non-delegating TDD, verification, debugging, and
> documentation workflows. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add narrative structure, temporal character state, information disclosure, knowledge, episode references, and the Phase 2 MCP surface on top of the Phase 1 foundation.

**Architecture:** Keep chapter, episode, and scene persistence in repositories and domain rules in services. Temporal state and knowledge are resolved by bounded service queries, while episode references are exposed through a unified tool family over separate relation tables.

**Tech Stack:** Python 3.10+, official MCP Python SDK v2, standard-library `sqlite3`, explicit SQL migrations, pytest, and stdio transport.

**Spec:** `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`

## Global Constraints

- Keep all implementation, migration, and test paths under `MCP/`.
- Preserve the Phase 1 service/repository/MCP layering and tool contracts.
- Use the Python standard-library `sqlite3` module; no ORM or external database.
- `origin/main` baseline is `a57a0e38fef211866270e8787cf92473601a2203` and
  implementation branch is `codex/phase2-narrative-state`.
- Keep `001_initial.sql` and `002_search.sql` byte-for-byte immutable.
- `003_narrative.sql` is the only Phase 2 migration; never create
  `004_drafts.sql` or any later migration.
- Keep historical chronology, reader disclosure, character knowledge, and
  character state separate; never infer one table from another.
- Store character state as change rows and resolve effective state, knowledge,
  and relationships by `chapter.position`, then `episode.position`, never by
  episode-ID magnitude.
- Keep `truth_status` independent from character knowledge state.
- Require `expected_version` on mutable updates and reject stale writes with
  stable `VERSION_CONFLICT` errors.
- Use one transaction for reorder, canon mutation plus audit, temporal
  relationship transitions, disclosure moves, and reference mutations.
- Raw authoring/admin get/search/history reads may expose future or deprecated
  rows; only narrative-boundary reads exclude them.
- Phase 1 remains 23 tools, Phase 2 adds exactly 27 tools, and Phase 3 adds 0.
- Preserve the `MCP -> Service -> Repository -> SQLite` layering. No SQL in
  handlers or services.
- Do not implement `episode_context`, drafts, Phase 4 systems, web, widgets,
  ORM, embeddings, or real `data/story.db` population.
- Commit every task independently after its focused test suite passes.

### Task 0: Contract and documentation alignment

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`
- Modify: `docs/superpowers/plans/2026-08-26-novel-mcp-phase2-plan.md`

**Interfaces:**
- Consumes: merged Phase 1 at `a57a0e38fef211866270e8787cf92473601a2203`.
- Produces: the explicit Phase 2 schema, temporal, disclosure, tool-surface,
  raw-read, immutable-migration, and Phase 3 boundary contract.

- [ ] **Step 1: Replace stale Phase 1 status**

State that Phase 1 is implemented and merged, identify the main baseline, and
state that `001_initial.sql` and `002_search.sql` are immutable.

- [ ] **Step 2: Record the Phase 2 contract**

Document the exact hierarchy fields/status constraints, change-log state,
authoring guards, reader/knowledge separation, four reference tables,
inclusive/exclusive temporal relationship ranges, order-based effective reads,
atomic reorder/version rules, and the exact 27 Phase 2 tools.

- [ ] **Step 3: Clarify active versus authoring reads**

Explicitly permit future/deprecated rows in admin `get/search/history` tools
while reserving future/deprecated exclusion for effective/boundary reads and
the deferred Phase 3 `episode_context`.

- [ ] **Step 4: Self-review and commit**

Run `rg -n "pre-merge|unmerged|003_narrative|004_drafts|episode_context|Phase 2|Phase 3" docs/superpowers/specs docs/superpowers/plans/2026-08-26-novel-mcp-phase2-plan.md`,
resolve contradictions, then commit:

```bash
git add docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md docs/superpowers/plans/2026-08-26-novel-mcp-phase2-plan.md
git commit -m "docs: finalize Phase 2 implementation contract"
```

### Task 1: Narrative migration `003_narrative.sql`

**Files:**
- Create: `MCP/migrations/003_narrative.sql`
- Modify: `MCP/tests/test_database_lifecycle.py`
- Create: `MCP/tests/test_narrative_migration.py`

**Interfaces:**
- Consumes: the migration runner and Phase 1 tables from the Phase 1 plan.
- Produces: immutable `003_narrative.sql` defining `chapters`, `episodes`,
  `scenes`, `character_states`, `information_items`, `reader_disclosures`,
  `character_knowledge_events`, and the four episode reference tables.

- [ ] **Step 1: Write the failing test**

```python
def test_narrative_migration_creates_all_phase2_tables(database):
    names = {
        row[0]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "chapters", "episodes", "scenes", "character_states",
        "information_items", "reader_disclosures",
        "character_knowledge_events", "episode_characters",
        "episode_world_facts", "episode_timeline_events",
        "episode_information",
    } <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_narrative_migration.py -q`

Expected: FAIL because `003_narrative.sql` is absent and the migration runner
has no Phase 2 schema to apply.

- [ ] **Step 3: Write minimal implementation**

Define the Phase 2 tables with foreign keys to the Phase 1 work and entity
tables, explicit ordering fields for chapters, episodes, and scenes, version
columns for mutable narrative entities, and temporal episode references. Use
`position >= 1`, the three requested sibling uniqueness constraints, valid JSON
checks/defaults for state, notes, and foreshadowing, and the exact status
CHECKs. Keep reader disclosures and character knowledge events in separate
tables. Do not add draft tables in this migration.

Rebuild `relationships` within this migration so its old unique constraint is
removed and `valid_from_episode_id`/`valid_to_episode_id` are added. Copy every
existing row with its original `id`, `work_id`, description, canon status,
version, and timestamps, assigning NULL temporal bounds. Rebuild
`canon_decision_changes` to extend its entity-type CHECK to chapter, episode,
scene, and information_item while copying all existing rows.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_database_lifecycle.py MCP/tests/test_narrative_migration.py -q`

Expected: PASS, including ordered migration application, foreign-key checks,
and a second-open idempotency check.

- [ ] **Step 5: Validation**

Run: `rg -n "003_narrative|004_drafts|drafts" MCP/migrations MCP/tests`; inspect
the schema table list from a temporary database.

Expected: `003_narrative.sql` owns no draft table, the fixed migration order is
unchanged, and 001/002 bytes are unchanged.

- [ ] **Step 6: Commit**

```bash
git add MCP/migrations/003_narrative.sql MCP/tests/test_database_lifecycle.py MCP/tests/test_narrative_migration.py
git commit -m "feat: add narrative schema migration"
```

### Task 2: Chapter, Episode, and Scene CRUD

**Files:**
- Create: `MCP/src/novel_mcp/repositories/narrative_repository.py`
- Create: `MCP/src/novel_mcp/services/narrative_service.py`
- Create: `MCP/tests/test_narrative_service.py`

**Interfaces:**
- Consumes: `003_narrative.sql`, Phase 1 work scope, and optimistic locking.
- Produces: `create_chapter(title: str, production_status: str) -> ChapterRecord`,
  `update_chapter(chapter_id: int, expected_version: int, ...) -> ChapterRecord`,
  `create_episode(chapter_id: int, title: str, production_status: str) -> EpisodeRecord`,
  `get_episode(episode_id: int) -> EpisodeRecord`,
  `update_episode(episode_id: int, expected_version: int, ...) -> EpisodeRecord`,
  `create_scene(episode_id: int, summary: str) -> SceneRecord`,
  `get_scene(scene_id: int) -> SceneRecord`, and corresponding list methods.
  Chapter, episode, and scene CRUD must cover title, summary, purpose,
  production status, canon status, and their parent ids; episode create/update
  also covers `foreshadowing_notes`, persisted as valid JSON with default `[]`.
  All three records expose `position`, `version`, and timestamps.

- [ ] **Step 1: Write the failing test**

```python
def test_episode_crud_keeps_production_status_separate_from_canon(service):
    chapter = service.create_chapter("第一章", "planned")
    episode = service.create_episode(chapter.id, "第一話", "outlined")
    scene = service.create_scene(episode.id, "到着")

    assert episode.production_status == "outlined"
    assert scene.episode_id == episode.id
    assert episode.canon_status == "draft"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_narrative_service.py -q`

Expected: FAIL because narrative repositories and services are absent.

- [ ] **Step 3: Write minimal implementation**

Implement CRUD with explicit parent checks, configured-work checks, independent
`ProductionStatus` and `CanonStatus` fields, append positions, valid JSON
validation, version increments on updates, deterministic list order, and
`NOT_FOUND` for missing parents or entities. Keep SQL in
`narrative_repository.py` and all status validation in the service. Do not let
ordinary chapter/episode/scene updates mutate canonical content without the
canon reason/audit path added in Task 7.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_narrative_service.py -q`

Expected: PASS, including chapter/episode/scene CRUD, parent scope checks,
status independence, ordering defaults, and stale-version rejection.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_narrative_service.py -q`; inspect service
files with `rg -n "SELECT|INSERT|UPDATE|DELETE" MCP/src/novel_mcp/services`.

Expected: tests pass and service modules contain no SQL.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/narrative_repository.py MCP/src/novel_mcp/services/narrative_service.py MCP/tests/test_narrative_service.py
git commit -m "feat: add narrative entity CRUD"
```

### Task 3: Atomic chapter, episode, and scene reorder

**Files:**
- Modify: `MCP/src/novel_mcp/repositories/narrative_repository.py`
- Modify: `MCP/src/novel_mcp/services/narrative_service.py`
- Create: `MCP/tests/test_narrative_reorder.py`

**Interfaces:**
- Consumes: narrative records and parent relationships from Task 2.
- Produces: `reorder_chapter(chapter_id: int, target_position: int, expected_version: int) -> tuple[ChapterRecord, ...]`,
  `reorder_episode(episode_id: int, target_position: int, expected_version: int) -> tuple[EpisodeRecord, ...]`,
  and `reorder_scene(scene_id: int, target_position: int, expected_version: int) -> tuple[SceneRecord, ...]`.

- [ ] **Step 1: Write the failing test**

```python
def test_episode_reorder_is_atomic_when_target_is_invalid(service):
    episodes = create_three_episodes(service)
    before = service.list_episodes(episodes[0].chapter_id)

    with pytest.raises(ValidationError):
        service.reorder_episode(episodes[0].id, target_position=99, expected_version=1)

    assert service.list_episodes(episodes[0].chapter_id) == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_narrative_reorder.py -q`

Expected: FAIL because reorder methods and atomic position updates are absent.

- [ ] **Step 3: Write minimal implementation**

Validate the target position and moved-row expected version before opening a
transaction. Use distinct temporary negative positions, then shift sibling
positions and update the moved row in one transaction. Increment the version
for the moved row and every shifted sibling; a no-op leaves every version
unchanged. Return the complete ordered sibling list and roll back every
position/version if any write fails.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_narrative_reorder.py -q`

Expected: PASS, including moving forward, moving backward, no-op moves,
invalid positions, stale versions, and rollback after an injected write error.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_narrative_reorder.py -q`; inspect the
repository transaction helper and confirm one transaction covers all shifts.

Expected: no partially reordered sibling set is observable.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/narrative_repository.py MCP/src/novel_mcp/services/narrative_service.py MCP/tests/test_narrative_reorder.py
git commit -m "feat: add atomic narrative reorder"
```

### Task 4: Character State and effective-state resolution

**Files:**
- Create: `MCP/src/novel_mcp/repositories/character_state_repository.py`
- Create: `MCP/src/novel_mcp/services/character_state_service.py`
- Create: `MCP/tests/test_character_state_service.py`

**Interfaces:**
- Consumes: characters and episode ordering from Tasks 1–2.
- Produces: `set_state(character_id: int, episode_id: int, state: str, expected_version: int | None) -> CharacterStateRecord`,
  `get_effective_state(character_id: int, episode_id: int) -> CharacterStateRecord | None`,
  and `history(character_id: int) -> tuple[CharacterStateRecord, ...]`, plus
  relationship temporal create/update compatibility and an internal
  effective-relationship query. State exposes physical/emotional state,
  `beliefs_json`, `location_world_fact_id`, and `state_json`; knowledge is not
  stored in this table.

- [ ] **Step 1: Write the failing test**

```python
def test_effective_state_uses_latest_change_at_or_before_episode(service):
    character = service.create_character("主人公", None)
    first = service.create_episode_for_test(1, "第一話")
    twelfth = service.create_episode_for_test(12, "第十二話")
    eighteenth = service.create_episode_for_test(18, "第十八話")
    service.set_state(character.id, first.id, "initial", None)
    service.set_state(character.id, twelfth.id, "injured", None)
    service.set_state(character.id, eighteenth.id, "recovered", None)

    assert service.get_effective_state(character.id, twelfth.id).state == "injured"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_character_state_service.py -q`

Expected: FAIL because state storage and effective temporal resolution do not
yet exist.

- [ ] **Step 3: Write minimal implementation**

Persist only state changes, never an episode snapshot. Enforce valid JSON and
one canonical row per `(character_id, episode_id)`; creation uses
`expected_version=None`, while correction of an existing row requires its
current version. Resolve the row with the greatest `(chapter.position,
episode.position)` less than or equal to the requested narrative position,
with a deterministic row-id tie-breaker. Reject a request for an episode from a
different work and return no state when no prior change exists.

Extend Phase 1 relationship create/update inputs with nullable inclusive
`valid_from_episode_id` and exclusive `valid_to_episode_id`. Preserve existing
row values during migration, allow multiple non-overlapping ranges, reject
ambiguous overlap for the same source/target/type, and resolve effective
relationships by chapter/episode position rather than episode ID.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_character_state_service.py -q`

Expected: PASS, including initial state, intermediate resolution, future-state
exclusion, history ordering, invalid episode scope, and update conflicts.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_character_state_service.py -q`; inspect
the SQL query plan for the effective-state lookup on a temporary database.

Expected: the query selects at or before the requested episode and never reads
a later state row.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/character_state_repository.py MCP/src/novel_mcp/services/character_state_service.py MCP/tests/test_character_state_service.py
git commit -m "feat: resolve effective character state"
```

### Task 5: Information, Reader Disclosure, and Character Knowledge

**Files:**
- Create: `MCP/src/novel_mcp/repositories/information_repository.py`
- Create: `MCP/src/novel_mcp/repositories/disclosure_repository.py`
- Create: `MCP/src/novel_mcp/services/information_service.py`
- Create: `MCP/src/novel_mcp/services/knowledge_service.py`
- Create: `MCP/tests/test_information_service.py`
- Create: `MCP/tests/test_knowledge_service.py`

**Interfaces:**
- Consumes: characters, episodes, and narrative migration from Tasks 1–4.
- Produces: `create_information(statement: str, truth_status: str) -> InformationItemRecord`,
  `update_information(item_id: int, expected_version: int, ...) -> InformationItemRecord`,
  `set_reader_disclosure(item_id: int, episode_id: int) -> ReaderDisclosureRecord`,
  `set_character_knowledge(character_id: int, item_id: int, episode_id: int, state: str) -> CharacterKnowledgeEventRecord`,
  and `get_known_information(character_id: int, episode_id: int) -> tuple[InformationItemRecord, ...]`.
  Information records include `statement`, `truth_status`, `authoring_guard`,
  `notes_json`, `canon_status`, `importance`, `version`, and timestamps.

- [ ] **Step 1: Write the failing test**

```python
def test_reader_and_character_knowledge_have_independent_boundaries(service):
    item = service.create_information("国家AIの事前認識", "uncertain")
    episode_24 = service.create_episode_for_test(24, "第二十四話")
    episode_37 = service.create_episode_for_test(37, "第三十七話")
    character = service.create_character("主人公", None)

    service.set_reader_disclosure(item.id, episode_24.id)
    service.set_character_knowledge(character.id, item.id, episode_37.id, "knows")

    assert service.reader_context_before(item.id, episode_24.id) == ()
    assert service.get_known_information(character.id, episode_24.id) == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_information_service.py MCP/tests/test_knowledge_service.py -q`

Expected: FAIL because information, disclosure, and knowledge services are
absent.

- [ ] **Step 3: Write minimal implementation**

Validate `truth_status` against `true`, `false`, `uncertain`, and `subjective`,
`importance >= 0`, and `notes_json` with `json.loads`. Persist
`authoring_guard` as an explicit field; it may be returned as a guard but its
protected statement must not be exposed by any future context builder.
Validate knowledge states against `suspects`, `believes`, `knows`, `confirmed`,
`doubts`, and `rejected`. Resolve knowledge only from events at or before the
requested episode using chapter/episode order, include effective state,
effective event episode, and information item in the structured result, and
never substitute reader disclosures for character knowledge. `information_get`,
`information_search`, and `character_state_history` remain explicit authoring
reads and may return future/deprecated rows.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_information_service.py MCP/tests/test_knowledge_service.py -q`

Expected: PASS, including false and uncertain information, disclosure timing,
character-specific knowledge, state replacement, future-event exclusion, and
cross-work isolation.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_information_service.py MCP/tests/test_knowledge_service.py -q`; inspect table access to confirm reader and character events use separate repositories.

Expected: tests pass with no shared shortcut that collapses the two concepts.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/information_repository.py MCP/src/novel_mcp/repositories/disclosure_repository.py MCP/src/novel_mcp/services/information_service.py MCP/src/novel_mcp/services/knowledge_service.py MCP/tests/test_information_service.py MCP/tests/test_knowledge_service.py
git commit -m "feat: add information and knowledge tracking"
```

### Task 6: Episode references

**Files:**
- Create: `MCP/src/novel_mcp/repositories/episode_reference_repository.py`
- Create: `MCP/src/novel_mcp/services/episode_reference_service.py`
- Create: `MCP/tests/test_episode_reference_service.py`

**Interfaces:**
- Consumes: episodes, world facts, timeline events, information items, and
  characters from Tasks 1–5.
- Produces: `add_reference(episode_id: int, reference_type: str, target_id: int) -> EpisodeReferenceRecord`,
  `remove_reference(episode_id: int, reference_type: str, target_id: int) -> None`,
  and `list_references(episode_id: int, reference_type: str | None) -> tuple[EpisodeReferenceRecord, ...]`.

- [ ] **Step 1: Write the failing test**

```python
def test_episode_reference_service_unifies_supported_reference_types(service):
    episode = service.create_episode_for_test(1, "第一話")
    fact = service.create_world_fact("火山異常", None, None)
    event = service.create_timeline_event("2104-01-01", "検知", [])

    service.add_reference(episode.id, "world_fact", fact.id)
    service.add_reference(episode.id, "timeline_event", event.id)

    assert {row.reference_type for row in service.list_references(episode.id, None)} == {
        "world_fact", "timeline_event"
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_episode_reference_service.py -q`

Expected: FAIL because the unified reference service is absent.

- [ ] **Step 3: Write minimal implementation**

Map `character`, `world_fact`, `timeline_event`, and `information` reference
types to their dedicated tables. Validate `episode.work_id == target.work_id`
and configured work before any write, default character role to `participant`,
bound role strings, reject duplicate links, make removal idempotent with
`removed: true` for an existing link and `removed: false` otherwise, and
preserve deterministic list ordering/filtering. Keep each link in its canonical
table; `episode_information` must never stand in for reader disclosure.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_episode_reference_service.py -q`

Expected: PASS, including all supported target types, duplicate rejection,
removal, filtering, missing-target errors, and cross-work checks.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_episode_reference_service.py -q`; verify
that the service delegates SQL to `episode_reference_repository.py`.

Expected: the four database tables remain separate while the service interface
is unified.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/episode_reference_repository.py MCP/src/novel_mcp/services/episode_reference_service.py MCP/tests/test_episode_reference_service.py
git commit -m "feat: add episode reference operations"
```

### Task 7: Extend Canon Policy to Phase 2 entities

**Files:**
- Modify: `MCP/src/novel_mcp/repositories/canon_repository.py`
- Modify: `MCP/src/novel_mcp/services/canon_service.py`
- Modify: `MCP/src/novel_mcp/services/narrative_service.py`
- Modify: `MCP/src/novel_mcp/services/information_service.py`
- Modify: `MCP/tests/test_canon_service.py`
- Create: `MCP/tests/test_phase2_canon.py`

**Interfaces:**
- Consumes: Phase 1 canon transitions and Phase 2 narrative/information
  records.
- Produces: backward-compatible `canon_status_set` support for
  `world_fact`, `timeline_event`, `character`, `relationship`, `chapter`,
  `episode`, `scene`, and `information_item`; protected content mutations
  write canon decision/change rows in the same transaction.

- [ ] **Step 1: Write failing canon tests**

Add tests for `idea|draft -> canon`, canonical content mutation, and
`canon -> deprecated` requiring a non-empty reason; ordinary idea/draft edits
not requiring a reason; `deprecated -> canon` being rejected; and failed
mutations rolling back both the entity and its audit rows. Cover chapter,
episode, scene, and information item in addition to all Phase 1 entity types.

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m pytest MCP/tests/test_canon_service.py MCP/tests/test_phase2_canon.py -q`

Expected: FAIL because Phase 2 entity types are not accepted by the current
canon dispatch or audit CHECK.

- [ ] **Step 3: Implement the minimal policy extension**

Extend the forward-migrated `entity_type` CHECK and repository dispatch without
changing Phase 1 behavior. Require reason exactly for protected transitions and
canonical content changes, reject deprecated-to-canon, and perform entity plus
canon decision/change writes in one transaction. Ensure chapter/episode/scene/
information updates cannot bypass this path when canonical content changes.

- [ ] **Step 4: Run focused and Phase 1 regression tests**

Run: `python -m pytest MCP/tests/test_canon_service.py MCP/tests/test_phase2_canon.py MCP/tests/test_phase1_acceptance.py -q`

Expected: all canon tests pass with stable structured errors and no raw SQLite
exception text.

- [ ] **Step 5: Validate quality and commit**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
python scripts/check_source_size.py
git add MCP/src/novel_mcp/repositories/canon_repository.py MCP/src/novel_mcp/services/canon_service.py MCP/src/novel_mcp/services/narrative_service.py MCP/src/novel_mcp/services/information_service.py MCP/tests/test_canon_service.py MCP/tests/test_phase2_canon.py
git commit -m "feat: extend canon policy to Phase 2 entities"
```

### Task 8: Phase 2 MCP tools, acceptance, and final verification

**Files:**
- Modify: `MCP/src/novel_mcp/mcp_server.py`
- Create: `MCP/src/novel_mcp/phase2_tools.py`
- Create: `MCP/src/novel_mcp/phase1_tools.py` if needed for a
  behavior-preserving registration split
- Create: `MCP/tests/test_phase2_mcp_tools.py`
- Extend: `MCP/tests/test_phase2_mcp_tools.py` with Phase 2 acceptance coverage
- Modify: `.github/workflows/mcp-ci.yml` to run pytest with `-W error` while
  retaining push and pull_request triggers

**Interfaces:**
- Consumes: Phase 1 server factory and Phase 2 services from Tasks 1–7.
- Produces: registrations for the exact Phase 2 tool list in the design
  specification, including `episode_reference_add`,
  `episode_reference_remove`, and `episode_reference_list`. Every new tool has
  a non-empty `Use this when ...` description, Pydantic/Literal/Field bounds,
  and explicit MCP annotations. Phase 1 registrations and behavior remain
  unchanged; `mcp_server.py` stays at or below the 400-line target where a
  responsibility-based split permits it.

- [ ] **Step 1: Write the failing test**

```python
def test_phase2_server_adds_only_phase2_tools(server):
    assert {
        "chapter_create", "chapter_update", "chapter_reorder", "chapter_list",
        "episode_create", "episode_update", "episode_get", "episode_reorder",
        "episode_list", "scene_create", "scene_update", "scene_get",
        "scene_reorder", "scene_list", "episode_reference_add",
        "episode_reference_remove", "episode_reference_list", "character_state_set",
        "character_state_get", "character_state_history", "information_create",
        "information_update", "information_get", "information_search",
        "reader_disclosure_set", "character_knowledge_set",
        "character_knowledge_get",
    } == (server.tool_names() - PHASE1_TOOL_NAMES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_phase2_mcp_tools.py MCP/tests/test_phase2_acceptance.py -q`

Expected: FAIL because Phase 2 adapters and acceptance coverage are absent.

- [ ] **Step 3: Write minimal implementation**

Register the exact Phase 2 tools, delegate each call to its service, serialize
effective-state and knowledge results rather than raw rows, and preserve the
Phase 1 tool registrations. Map domain errors to the existing structured JSON
error model. Read tools use `readOnlyHint=true, destructiveHint=false`;
creates use both false; updates/reorders/removes/sets use read-only false,
open-world false; `episode_reference_remove` alone has destructive true. Do
not register Phase 3 tools.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_phase2_mcp_tools.py MCP/tests/test_phase2_acceptance.py -q`

Expected: PASS, including CRUD, reorder atomicity, effective state, knowledge
boundaries, reference operations, and tool-list checks.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests -W error -q`; inspect `server.tool_names()` and
confirm that no `episode_context`, outline, or draft tool is registered. Then
run the required repository gates:

```powershell
cd MCP
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
git diff --exit-code origin/main -- MCP/migrations/001_initial.sql MCP/migrations/002_search.sql
Test-Path MCP/migrations/004_drafts.sql
```

Expected: all Phase 1 and Phase 2 tests pass with zero Python warnings,
coverage is at least 80%, the immutable migration diff is empty, and the last
command prints `False`. Capture the maximum production Python path/lines/bytes
and maximum test path/lines.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/mcp_server.py MCP/src/novel_mcp/phase2_tools.py MCP/tests/test_phase2_mcp_tools.py MCP/tests/test_phase2_acceptance.py
git commit -m "feat: expose Phase 2 MCP tools"
```
