# Novel MCP Phase 1 Implementation Plan

> Execution policy: ChatGPT owns architecture, design, and review. Codex Luna
> performs sequential implementation and verification. Subagent dispatch or
> model escalation occurs only when the user explicitly requests it.
> Superpowers are limited to non-delegating TDD, verification, debugging, and
> documentation workflows. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational Novel Production MCP database lifecycle, core canon repositories and services, Japanese search baseline, and Phase 1 stdio tools on a reproducible repository development foundation.

**Architecture:** Keep MCP handlers thin and delegate to services, which own validation and transactions, while repositories own SQLite queries. One configured MCP instance uses one story database, and all implementation files remain under `MCP/`.

**Tech Stack:** Python 3.10+, the concrete CI Python version in `.python-version`, `uv`, official MCP Python SDK v2, standard-library `sqlite3`, explicit SQL migrations, pytest/pytest-cov, Ruff, mypy, pre-commit, and stdio transport.

**Spec:** `docs/superpowers/specs/2026-08-26-novel-production-mcp-design.md`

## Global Constraints

- Keep the implementation paths under `MCP/`.
- Use the service/repository/MCP layering; MCP handlers contain no SQL.
- Use Python standard-library `sqlite3`; do not add an ORM.
- SQLite remains the canonical source of truth.
- Use one configured database per MCP instance; do not expose `work_id` in ordinary tool arguments.
- Apply `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`, and `PRAGMA busy_timeout = 5000` to every connection.
- Keep `001_initial.sql`, `002_search.sql`, `003_narrative.sql`, and `004_drafts.sql` immutable after application.
- Preserve the independent `CanonStatus` and `ProductionStatus` value sets.
- Require `expected_version` for mutable-entity updates and reject stale values with `VERSION_CONFLICT`.
- Require a reason for protected canon transitions and canonical content changes.
- Keep Phase 1 `works` metadata normalized as `working_title`, `genre`,
  `premise`, valid-JSON `themes_json`, `description`, and constrained
  `production_status` (`planned|outlined|drafting|revising|final`), alongside
  `slug`, `version`, and timestamps.
- Use `MCP/pyproject.toml` and `MCP/uv.lock` as the authoritative Python dependency files; `uv sync --all-groups` must reproduce the development environment.
- Keep the repository Python version concrete and synchronized between `.python-version` and GitHub Actions.
- Use Ruff for linting and formatting, strict-by-default mypy with only narrowly justified exceptions, pytest with an 80% Phase 1 coverage target, and lightweight pre-commit checks.
- Keep repository text files UTF-8 with LF endings, final newlines, and no trailing whitespace through `.editorconfig` and validation.
- Use standard-library `logging` for diagnostic events without logging novel prose, secret settings, episode context, private notes, or draft bodies.
- Production Python modules under `MCP/src/**/*.py` must be at most 600 lines and 40 KiB; test modules under `MCP/tests/**/*.py` must be at most 800 lines. The SHOULD limits are 400 and 500 lines respectively. Generated files, `uv.lock`, migration SQL, fixtures, snapshots, and vendored code are exempt from the automated size gate.
- The source-size hard limits must be enforced by a small repository script in CI; SHOULD-limit exceedance is a warning.
- GitHub Actions must validate `uv sync`, Ruff check/format, mypy, pytest, and the source-size gate on pushes and pull requests.
- Commit every task independently after its focused test suite passes.

### Task 1: Repository Development Foundation, configuration, and SQLite database lifecycle

**Files:**
- Create: `MCP/migrations/001_initial.sql`
- Create: `.editorconfig`
- Create: `.python-version`
- Create: `.github/workflows/mcp-ci.yml`
- Create: `MCP/.pre-commit-config.yaml`
- Create: `MCP/scripts/check_source_size.py`
- Modify: `MCP/pyproject.toml`
- Create: `MCP/src/novel_mcp/config.py`
- Create: `MCP/src/novel_mcp/database.py`
- Create: `MCP/src/novel_mcp/errors.py`
- Create: `MCP/src/novel_mcp/__init__.py`
- Create: `MCP/tests/test_database_lifecycle.py`
- Create: `MCP/tests/test_development_foundation.py`

**Interfaces:**
- Consumes: database path and migration directory supplied by `DatabaseConfig`.
- Produces: `DatabaseConfig(db_path: Path, migration_dir: Path)`,
  `open_database(config: DatabaseConfig) -> sqlite3.Connection`,
  `apply_migrations(connection: sqlite3.Connection, migration_dir: Path) -> tuple[str, ...]`,
  and the Phase 1 core tables listed by the design specification.
- Produces a reproducible `uv.lock`, concrete Python version declaration,
  Ruff/mypy/pytest/pre-commit configuration, GitHub Actions checks, diagnostic
  logging setup, and the source-size hard-limit checker.

- [ ] **Step 1: Write the failing test**

```python
def test_open_database_applies_connection_defaults_and_migrations(tmp_path):
    config = DatabaseConfig(tmp_path / "story.db", Path("MCP/migrations"))
    connection = open_database(config)

    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert connection.execute(
        "SELECT version FROM schema_migrations"
    ).fetchone()[0] == "001_initial.sql"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd MCP; uv run pytest tests/test_database_lifecycle.py::test_open_database_applies_connection_defaults_and_migrations -q`

Expected: FAIL because the lifecycle module and `001_initial.sql` do not yet exist.

- [ ] **Step 3: Write minimal implementation**

Implement `DatabaseConfig`, configure all three pragmas on a new connection,
run migration files in lexical order inside a transaction, record each applied
filename in `schema_migrations`, and add the core Phase 1 tables from the
specification. Reject a migration filename that has already been applied with
different bytes. Keep `001_initial.sql` limited to Phase 1 core schema.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd MCP; uv run pytest tests/test_database_lifecycle.py -q`

Expected: PASS, including a second-open idempotency test and a migration
failure rollback test.

- [ ] **Step 5: Validation**

Run: `cd MCP; uv run pytest tests/test_development_foundation.py -q; uv run ruff check .; uv run ruff format --check .; uv run mypy src; uv run pre-commit run --all-files`; then run `python MCP/scripts/check_source_size.py` from the repository root and inspect the migration inventory with `Get-ChildItem MCP/migrations`.

Expected: development checks and source-size validation succeed, and only
`001_initial.sql` is present for this task.

- [ ] **Step 6: Commit**

```bash
git add .editorconfig .python-version .github/workflows/mcp-ci.yml MCP/.pre-commit-config.yaml MCP/pyproject.toml MCP/uv.lock MCP/scripts/check_source_size.py MCP/migrations/001_initial.sql MCP/src/novel_mcp MCP/tests/test_database_lifecycle.py MCP/tests/test_development_foundation.py
git commit -m "chore: establish MCP development foundation"
```

### Task 2: Work metadata repository, service, and novel-init

**Files:**
- Create: `MCP/src/novel_mcp/repositories/work_repository.py`
- Create: `MCP/src/novel_mcp/services/work_service.py`
- Create: `MCP/src/novel_mcp/cli.py`
- Modify: `MCP/pyproject.toml`
- Create: `MCP/tests/test_work_service.py`
- Create: `MCP/tests/test_novel_init.py`

**Interfaces:**
- Consumes: `open_database`, the `works` table, and `DatabaseConfig` from Task 1.
- Produces: `WorkRepository.get() -> WorkRecord | None`,
  `WorkRepository.update(expected_version: int, fields: Mapping[str, object])
  -> WorkRecord`, `WorkService.get() -> WorkRecord`,
  `WorkService.update(working_title: str, expected_version: int, ...metadata)
  -> WorkRecord`, and `initialize_work(db_path: Path, working_title: str, ...)
  -> WorkRecord` exposed by the `novel-init` console script.

- [ ] **Step 1: Write the failing test**

```python
def test_initialize_work_is_explicit_and_update_requires_version(tmp_path):
    record = initialize_work(tmp_path / "story.db", "2126")
    assert record.working_title == "2126"
    assert record.version == 1

    service = WorkService(open_test_database(tmp_path / "story.db"))
    updated = service.update("2126 revised", expected_version=1)
    assert updated.version == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_work_service.py -q`

Expected: FAIL because no work repository, service, or initializer exists.

- [ ] **Step 3: Write minimal implementation**

Create exactly one work during `initialize_work`; normal database opening must
not create one. Require a non-empty working title, validate metadata and
`themes_json`, use the repository conditional update for `expected_version`,
and map an affected-row count of zero to `VERSION_CONFLICT`. Register
`novel-init` with `--db`, `--working-title` (keeping `--title` as an input
alias), and the normalized metadata options.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_work_service.py MCP/tests/test_novel_init.py -q`

Expected: PASS, including no implicit work on ordinary startup, duplicate
initialization rejection, and stale-version rejection.

- [ ] **Step 5: Validation**

Run: `python -m pip install --dry-run -e MCP` in an environment with the
official dependency index configured, then inspect `MCP/pyproject.toml`.

Expected: package metadata resolves without adding a runtime command other
than the explicitly named `novel-init` command.

- [ ] **Step 6: Commit**

```bash
git add MCP/pyproject.toml MCP/src/novel_mcp/repositories/work_repository.py MCP/src/novel_mcp/services/work_service.py MCP/src/novel_mcp/cli.py MCP/tests/test_work_service.py MCP/tests/test_novel_init.py
git commit -m "feat: add explicit work initialization"
```

### Task 3: World Fact CRUD, temporal validity, and search

**Files:**
- Create: `MCP/migrations/002_search.sql`
- Create: `MCP/src/novel_mcp/repositories/world_fact_repository.py`
- Create: `MCP/src/novel_mcp/services/world_fact_service.py`
- Create: `MCP/tests/test_world_fact_service.py`

**Interfaces:**
- Consumes: the configured-work scope, transaction boundary, and optimistic
  locking error mapping from Tasks 1–2.
- Produces: `WorldFactService.create(statement: str, valid_from: str | None, valid_to: str | None) -> WorldFactRecord`,
  `get(fact_id: int) -> WorldFactRecord`,
  `update(fact_id: int, statement: str, expected_version: int, reason: str | None = None) -> WorldFactRecord`,
  and `search(query: str, limit: int) -> tuple[WorldFactRecord, ...]`.

- [ ] **Step 1: Write the failing test**

```python
def test_world_fact_update_rejects_stale_version_and_search_is_scoped(service):
    fact = service.create("火山異常は2104年に検知された", None, None)
    assert service.search("火山", limit=10) == (fact,)

    with pytest.raises(VersionConflict):
        service.update(fact.id, "変更", expected_version=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_world_fact_service.py -q`

Expected: FAIL because world-fact persistence and service validation do not yet
exist.

- [ ] **Step 3: Write minimal implementation**

Keep `001_initial.sql` immutable. Use `002_search.sql` for the additive nullable
`valid_from`/`valid_to` columns and rebuildable world-fact search indexes needed
by the Phase 1 service. The service-facing `statement` is stored as the
authoritative `body` (and the legacy required `title` adapter field), while an
opaque internal `fact_key` and the initial `draft` canon status are generated
below the ordinary service input boundary. Do not expose those schema adapter
fields in the Task 3 interface. Validate temporal bounds before writing,
preserve the configured work scope, increment `version` only after a matching
conditional update, and return `NOT_FOUND` for an absent fact. Use
deterministic ordering for search results and keep the query implementation in
the repository.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_world_fact_service.py -q`

Expected: PASS, including create/get/update, invalid ranges, empty results,
cross-work isolation, and optimistic locking.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_world_fact_service.py -q`; verify with
`rg -n "SELECT|INSERT|UPDATE|DELETE" MCP/src/novel_mcp/services`.

Expected: all tests pass and no SQL appears in the service module.

- [ ] **Step 6: Commit**

```bash
git add MCP/migrations/002_search.sql MCP/src/novel_mcp/repositories/world_fact_repository.py MCP/src/novel_mcp/services/world_fact_service.py MCP/tests/test_world_fact_service.py
git commit -m "feat: add world fact service"
```

### Task 4: Timeline events, range queries, participants, and relations

**Files:**
- Create: `MCP/src/novel_mcp/repositories/timeline_repository.py`
- Create: `MCP/src/novel_mcp/services/timeline_service.py`
- Create: `MCP/tests/test_timeline_service.py`

**Interfaces:**
- Consumes: configured-work scope and core timeline tables from Task 1.
- Produces: `create_event(...) -> TimelineEventRecord`,
  `get_event(event_id: int) -> TimelineEventRecord`,
  `update_event(event_id: int, expected_version: int, ..., reason: str | None = None) -> TimelineEventRecord`,
  `search_events(query: str, limit: int) -> tuple[TimelineEventRecord, ...]`,
  `range_events(start: str, end: str, limit: int) -> tuple[TimelineEventRecord, ...]`,
  `move_event(event_id: int, expected_version: int, new_date: str) -> TimelineEventRecord`,
  and `create_relation(source_id: int, target_id: int, relation_type: str) -> TimelineRelationRecord`.

- [ ] **Step 1: Write the failing test**

```python
def test_timeline_range_orders_events_and_relation_is_transactional(service):
    first = service.create_event("2104-01-01", "検知", participants=[])
    second = service.create_event("2104-02-01", "発表", participants=[])

    assert service.range_events("2104-01-01", "2104-12-31", limit=30) == (first, second)
    relation = service.create_relation(first.id, second.id, "causes")
    assert relation.source_event_id == first.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_timeline_service.py -q`

Expected: FAIL because timeline persistence, range ordering, participant links,
and relation creation are absent.

- [ ] **Step 3: Write minimal implementation**

Keep historical date values in `timeline_events.chronology_sort_key`, map the
service title to both the legacy `title` and `summary` fields, generate an
opaque internal `event_key`, and default the hidden schema adapter's
`canon_status` to `draft`. Map participant `(label, role)` values to the
existing participant-link table. Validate inclusive range boundaries, enforce
same-work foreign keys, and use a single transaction for an event plus
participant links. Reject self-relations and duplicate relation edges using
structured validation errors.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_timeline_service.py -q`

Expected: PASS, including move version checks, range bounds, participant
links, relation rollback, and cross-work rejection.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_timeline_service.py -q`; inspect query
ownership with `rg -n "SELECT|INSERT|UPDATE|DELETE" MCP/src/novel_mcp`.

Expected: tests pass and SQL remains in repository modules only.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/timeline_repository.py MCP/src/novel_mcp/services/timeline_service.py MCP/tests/test_timeline_service.py
git commit -m "feat: add timeline event operations"
```

### Task 5: Characters and directional relationships

**Files:**
- Create: `MCP/src/novel_mcp/repositories/character_repository.py`
- Create: `MCP/src/novel_mcp/repositories/relationship_repository.py`
- Create: `MCP/src/novel_mcp/services/character_service.py`
- Create: `MCP/src/novel_mcp/services/relationship_service.py`
- Create: `MCP/tests/test_character_service.py`
- Create: `MCP/tests/test_relationship_service.py`

**Interfaces:**
- Consumes: configured-work scope and optimistic-locking primitives from Tasks 1–4.
- Produces: `CharacterService.create(name: str, profile: str | None) -> CharacterRecord`,
  `get(character_id: int) -> CharacterRecord`,
  `update(character_id: int, expected_version: int, ..., reason: str | None = None) -> CharacterRecord`,
  `search(query: str, limit: int) -> tuple[CharacterRecord, ...]`,
  `RelationshipService.create(source_character_id: int, target_character_id: int, relation_type: str) -> RelationshipRecord`,
  `update(relationship_id: int, expected_version: int, relation_type: str, reason: str | None = None) -> RelationshipRecord`,
  and `search(character_id: int | None, limit: int) -> tuple[RelationshipRecord, ...]`.

- [ ] **Step 1: Write the failing test**

```python
def test_relationship_direction_is_preserved(service):
    protagonist = service.character.create("主人公", None)
    mentor = service.character.create("師匠", None)
    relation = service.relationship.create(protagonist.id, mentor.id, "trusts")

    assert relation.source_character_id == protagonist.id
    assert relation.target_character_id == mentor.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_character_service.py MCP/tests/test_relationship_service.py -q`

Expected: FAIL because character and relationship services do not yet exist.

- [ ] **Step 3: Write minimal implementation**

Use the immutable `characters` schema adapter by mapping public `name` to
`display_name`, public `profile` to `summary` (empty when omitted), generating
an opaque `character_key`, and defaulting hidden `canon_status` to `draft`.
For relationships, map the public `relation_type` to `relationship_type`, use
an empty hidden `summary`, and keep hidden `canon_status` at `draft`. Store
relationship direction explicitly; do not infer reciprocal edges. Apply the
same `expected_version` compare-and-set rule to character and relationship
updates. Validate both endpoints belong to the configured work before the
relationship transaction begins.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_character_service.py MCP/tests/test_relationship_service.py -q`

Expected: PASS, including directional reads, stale updates, missing endpoints,
search ordering, and cross-work isolation.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_character_service.py MCP/tests/test_relationship_service.py -q`; verify no relationship service file contains SQL.

Expected: all tests pass and repository ownership remains clear.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/character_repository.py MCP/src/novel_mcp/repositories/relationship_repository.py MCP/src/novel_mcp/services/character_service.py MCP/src/novel_mcp/services/relationship_service.py MCP/tests/test_character_service.py MCP/tests/test_relationship_service.py
git commit -m "feat: add characters and relationships"
```

### Task 6: Canon decisions and atomic canonical mutation

**Files:**
- Create: `MCP/src/novel_mcp/repositories/canon_repository.py`
- Create: `MCP/src/novel_mcp/services/canon_service.py`
- Create: `MCP/tests/test_canon_service.py`

**Interfaces:**
- Consumes: mutable entity repositories, status values, and transaction boundary from Tasks 1–5.
- Produces: `set_canon_status(entity_type: str, entity_id: int, target_status: str, expected_version: int, reason: str | None) -> CanonDecisionRecord`,
  `update_content(entity_type: str, entity_id: int, fields: Mapping[str, object], expected_version: int, reason: str | None) -> CanonDecisionRecord`,
  `record_decision(summary: str, reason: str, changes: Sequence[CanonChange]) -> CanonDecisionRecord`,
  `get_decision(decision_id: int) -> CanonDecisionRecord`, and
  `search_decisions(query: str, limit: int) -> tuple[CanonDecisionRecord, ...]`.

- [ ] **Step 1: Write the failing test**

```python
def test_canon_transition_requires_reason_and_commits_decision_atomically(service):
    fact = service.world_fact.create("旧記述", None, None)

    with pytest.raises(CanonReasonRequired):
        service.canon.set_canon_status("world_fact", fact.id, "canon", 1, None)

    decision = service.canon.set_canon_status(
        "world_fact", fact.id, "canon", 1, "採用理由"
    )
    assert decision.changes[0].entity_id == fact.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_canon_service.py -q`

Expected: FAIL because canon policy and decision history are not implemented.

- [ ] **Step 3: Write minimal implementation**

Validate static entity/status fields before opening the write transaction, then
begin before taking the entity snapshot so caller `expected_version` is checked
against the same transaction that performs the conditional mutation. Generate
the immutable schema's opaque `decision_key` and use its `decided_at` timestamp
below the public interface. Persist one decision and all change rows in the
same transaction as the target mutation; repository methods own all SQL while
the service owns validation and transaction boundaries. Roll back the target
mutation if any decision row fails. Keep `canon_decisions` separate from
`canon_decision_changes`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_canon_service.py -q`

Expected: PASS, including multiple entity changes, missing reasons, rollback,
decision retrieval, and independent production-status behavior.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_canon_service.py -q`; review transaction
boundaries with `rg -n "BEGIN|COMMIT|ROLLBACK|transaction" MCP/src/novel_mcp/services`.

Expected: all canon writes use one service-owned transaction.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/repositories/canon_repository.py MCP/src/novel_mcp/services/canon_service.py MCP/tests/test_canon_service.py
git commit -m "feat: enforce canon decision history"
```

### Task 7: Japanese text search baseline

**Files:**
- Create: `MCP/src/novel_mcp/repositories/search_repository.py`
- Create: `MCP/src/novel_mcp/services/search_service.py`
- Create: `MCP/tests/test_japanese_search.py`

**Interfaces:**
- Consumes: canonical text rows and migration runner from Tasks 1–6.
- Consumes the immutable `002_search.sql` additive validity/index migration
  created in Task 3; Task 7 must not rewrite an applied migration.
- Produces: `SearchService.search_world_facts(query: str, limit: int) -> tuple[WorldFactRecord, ...]`,
  `search_characters(query: str, limit: int) -> tuple[CharacterRecord, ...]`,
  and deterministic empty-query behavior that returns an empty tuple.

- [ ] **Step 1: Write the failing test**

```python
def test_japanese_search_matches_text_and_has_stable_order(database):
    insert_fact(database, "国家AIが火山異常を検知")
    insert_fact(database, "火山異常は翌日に公表された")

    rows = SearchService(database).search_world_facts("火山異常", limit=30)

    assert [row.statement for row in rows] == [
        "国家AIが火山異常を検知",
        "火山異常は翌日に公表された",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_japanese_search.py -q`

Expected: FAIL because `002_search.sql` and the search repository do not exist.

- [ ] **Step 3: Write minimal implementation**

Do not modify `002_search.sql`. Implement the selected SQLite text-search
strategy behind `SearchRepository`, using the rebuildable structures already
created there and a parameterized `LIKE` fallback when the available SQLite
build does not provide the preferred tokenizer. Preserve work scope, normalize
the empty query to no results, cap `limit` at the service bound, and use a
stable tie-breaker for equal matches. Keep canonical rows as the only
authoritative data.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_japanese_search.py -q`

Expected: PASS, including Japanese phrases, no-match queries, empty queries,
limit bounds, stable ordering, and rebuildability from canonical rows.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests/test_database_lifecycle.py MCP/tests/test_japanese_search.py -q`; verify migration order with `Get-ChildItem MCP/migrations | Sort-Object Name`.

Expected: both migrations apply once in lexical order and search tests pass.

- [ ] **Step 6: Commit**

```bash
git add MCP/migrations/002_search.sql MCP/src/novel_mcp/repositories/search_repository.py MCP/src/novel_mcp/services/search_service.py MCP/tests/test_japanese_search.py
git commit -m "feat: add Japanese text search baseline"
```

### Task 8: Phase 1 MCP stdio tool surface

**Files:**
- Create: `MCP/src/novel_mcp/mcp_server.py`
- Create: `MCP/src/novel_mcp/tool_errors.py`
- Create: `MCP/tests/test_phase1_mcp_tools.py`
- Create: `MCP/tests/test_phase1_acceptance.py`

**Interfaces:**
- Consumes: Phase 1 service classes from Tasks 1–7.
- Produces: `create_server(config: DatabaseConfig) -> MCPServer`, tool
  registrations for every Phase 1 name in the design specification, and
  structured JSON success/error payloads over stdio.

- [ ] **Step 1: Write the failing test**

```python
def test_phase1_server_registers_only_planned_tools(server):
    assert server.tool_names() == {
        "work_get", "work_update", "world_fact_create", "world_fact_update",
        "world_fact_get", "world_fact_search", "timeline_event_create",
        "timeline_event_update", "timeline_event_get", "timeline_event_search",
        "timeline_range", "timeline_move", "timeline_relation_create",
        "character_create", "character_update", "character_get",
        "character_search", "relationship_create", "relationship_update",
        "relationship_search", "canon_status_set", "canon_decision_get",
        "canon_decision_search",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest MCP/tests/test_phase1_mcp_tools.py MCP/tests/test_phase1_acceptance.py -q`

Expected: FAIL because no MCP server or tool adapter exists.

- [ ] **Step 3: Write minimal implementation**

Build the SDK server in `mcp_server.py`, register only the Phase 1 tools, map
validated inputs to service calls, serialize records to JSON-compatible values,
and map domain exceptions to the structured error model. Keep SQL and
connection management below the service boundary. Do not add Phase 2 or Phase
3 tool names.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest MCP/tests/test_phase1_mcp_tools.py MCP/tests/test_phase1_acceptance.py -q`

Expected: PASS, including tool registration against a literal expected Phase 1
set, successful structured output, validation errors, stale-version errors,
canon reason errors, direct timeline retrieval beyond the range default limit,
and no future phase tools.

- [ ] **Step 5: Validation**

Run: `python -m pytest MCP/tests -q`; run the SDK's stdio protocol smoke test
with an isolated temporary database and no repository `story.db` path.

Expected: all Phase 1 tests pass, the process speaks stdio, and no database
file is generated in the repository working tree.

- [ ] **Step 6: Commit**

```bash
git add MCP/src/novel_mcp/mcp_server.py MCP/src/novel_mcp/tool_errors.py MCP/tests/test_phase1_mcp_tools.py MCP/tests/test_phase1_acceptance.py
git commit -m "feat: expose Phase 1 MCP tools"
```

## PR #1 specification-alignment correction

The unmerged PR review requires the approved normalized Phase 1 data model,
non-exact timeline ranges, SQLite invariants, trigram-first search, explicit
canon transition/noise policy, and MCP descriptions/schemas. The detailed
inline execution plan is
`docs/superpowers/plans/2026-08-26-novel-mcp-phase1-pr1-review-fixes.md`.
It corrects the pre-merge `001_initial.sql`/`002_search.sql` bytes in place,
keeps future `003_narrative.sql`/`004_drafts.sql` responsibilities untouched,
and does not expand the 23-tool Phase 1 boundary.
