# Novel MCP Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add narrative structure, temporal character state, information disclosure, knowledge, episode references, and the Phase 2 MCP surface on top of the Phase 1 foundation.

**Architecture:** Keep chapter, episode, and scene persistence in repositories and domain rules in services. Temporal state and knowledge are resolved by bounded service queries, while episode references are exposed through a unified tool family over separate relation tables.

**Tech Stack:** Python 3.10+, official MCP Python SDK v2, standard-library `sqlite3`, explicit SQL migrations, pytest, and stdio transport.

**Spec:** `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`

## Global Constraints

- Keep all implementation, migration, and test paths under `MCP/`.
- Preserve the Phase 1 service/repository/MCP layering and tool contracts.
- Use the Python standard-library `sqlite3` module; no ORM or external database.
- Keep `003_narrative.sql` immutable after it is applied.
- Keep historical chronology, reader disclosure, and character knowledge separate.
- Store character state as change rows; resolve effective state at a requested episode.
- Keep `truth_status` independent from character knowledge state.
- Require `expected_version` on mutable updates and reject stale writes with `VERSION_CONFLICT`.
- Use one transaction for atomic reorder operations and multi-row reference mutations.
- Exclude future episode data and deprecated canon from active reads.
- Commit every task independently after its focused test suite passes.

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
columns for mutable narrative entities, and temporal episode references. Keep
reader disclosures and character knowledge events in separate tables. Do not
add draft tables in this migration.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_database_lifecycle.py MCP/tests/test_narrative_migration.py -q`

Expected: PASS, including ordered migration application, foreign-key checks,
and a second-open idempotency check.

- [ ] **Step 5: Validation**

Run: `rg -n "003_narrative|004_drafts|drafts" MCP/migrations MCP/tests`; inspect
the schema table list from a temporary database.

Expected: `003_narrative.sql` owns no draft table and the fixed migration order
is unchanged.

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

Implement CRUD with explicit parent checks, independent `ProductionStatus` and
`CanonStatus` fields, version increments on updates, deterministic list order,
and `NOT_FOUND` for missing parents or entities. Keep SQL in
`narrative_repository.py` and all status validation in the service.

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

Validate the target position and expected version before opening a transaction,
shift sibling positions in one transaction, update the moved row, and return
the complete ordered sibling list. Roll back every position if any write fails.

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
  and `history(character_id: int) -> tuple[CharacterStateRecord, ...]`.

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

Persist only state changes, never an episode snapshot. Resolve the row with the
greatest episode position less than or equal to the requested episode position,
with a deterministic row-id tie-breaker. Reject a request for an episode from a
different work and return no state when no prior change exists.

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

Validate `truth_status` against `true`, `false`, `uncertain`, and `subjective`.
Validate knowledge states against `suspects`, `believes`, `knows`, `confirmed`,
`doubts`, and `rejected`. Resolve knowledge only from events at or before the
requested episode and never substitute reader disclosures for character
knowledge.

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
types to their dedicated tables. Validate target existence and work scope,
reject duplicate links, make removal idempotent only when the link is absent,
and preserve deterministic list ordering.

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

### Task 7: Phase 2 MCP tools and acceptance test

**Files:**
- Modify: `MCP/src/novel_mcp/mcp_server.py`
- Create: `MCP/src/novel_mcp/phase2_tools.py`
- Create: `MCP/tests/test_phase2_mcp_tools.py`
- Create: `MCP/tests/test_phase2_acceptance.py`

**Interfaces:**
- Consumes: Phase 1 server factory and Phase 2 services from Tasks 1–6.
- Produces: registrations for the exact Phase 2 tool list in the design
  specification, including `episode_reference_add`,
  `episode_reference_remove`, and `episode_reference_list`.

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
    } <= server.tool_names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_phase2_mcp_tools.py MCP/tests/test_phase2_acceptance.py -q`

Expected: FAIL because Phase 2 adapters and acceptance coverage are absent.

- [ ] **Step 3: Write minimal implementation**

Register the exact Phase 2 tools, delegate each call to its service, serialize
effective-state and knowledge results rather than raw rows, and preserve the
Phase 1 tool registrations. Map domain errors to the existing structured JSON
error model. Do not register Phase 3 tools.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_phase2_mcp_tools.py MCP/tests/test_phase2_acceptance.py -q`

Expected: PASS, including CRUD, reorder atomicity, effective state, knowledge
boundaries, reference operations, and tool-list checks.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests -q`; inspect `server.tool_names()` and confirm
that no `episode_context` or draft tool is registered.

Expected: all Phase 1 and Phase 2 tests pass and Phase 3 remains absent.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/mcp_server.py MCP/src/novel_mcp/phase2_tools.py MCP/tests/test_phase2_mcp_tools.py MCP/tests/test_phase2_acceptance.py
git commit -m "feat: expose Phase 2 MCP tools"
```
