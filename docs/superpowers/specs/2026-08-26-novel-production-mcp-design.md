# Novel Production MCP Design Specification

**Status:** Approved architecture for the initial repository bootstrap

**Date:** 2026-08-26

## Purpose

Novel Production MCP is a tool-only MCP component for maintaining a structured
novel-production database. The component will provide bounded, transactional
operations over story canon, historical chronology, narrative structure,
character state, information disclosure, and append-only episode drafts.

This specification defines the Phase 1–3 architecture and the invariants that
future implementation must preserve. The initial repository commit contains
this specification and implementation plans only; it does not contain the MCP
server, SQLite schema, migrations, or tools.

## Architecture

The runtime follows a strict inward flow:

```text
MCP Tool Layer
    ↓
Service Layer
    ↓
Repository Layer
    ↓
SQLite
```

- MCP tool handlers translate structured tool input and output. They do not
  contain SQL.
- Services own domain validation, transactions, canon policy, bounded context
  assembly, and error mapping.
- Repositories own SQL, row mapping, and database-specific query behavior.
- SQLite is the canonical source of truth. Markdown and HTML are export formats
  and are never authoritative inputs to the domain model.
- Phase 1–3 uses the Python standard-library `sqlite3` module and no ORM.
- Vector databases and embeddings are outside the Phase 1–3 architecture.

One MCP instance is configured with one target story database. The database
schema retains `works` for future import/export and testing scenarios, but
ordinary MCP tool arguments do not expose `work_id`. The target database is
fixed at MCP startup configuration time.

## Scope Boundary

In scope for the Phase 1–3 design:

- Repository-wide monorepo shape with `MCP/`, `data/`, and `docs/` at root.
- SQLite lifecycle, explicit migrations, and database defaults.
- Work, world fact, timeline, character, relationship, canon decision,
  chapter, episode, scene, information, disclosure, knowledge, context, and
  append-only draft concepts listed in this document.
- Structured JSON MCP tool output over stdio.
- Optimistic locking for mutable entities.
- Separation of historical truth from reader and character knowledge.
- Bounded episode context that cannot leak future or deprecated information.

Out of scope:

- Web UI, widgets, ChatGPT Apps UI, or a browser client.
- Production deployment, CI/CD, Docker, release management, and hosting.
- ORM, vector search, embeddings, or an external search service.
- Automatic story creation during ordinary MCP startup.
- A generated `story.db` in the repository.
- Any live writing workflow before the Phase 3 acceptance gate.

## Status Models

Canon status and production status are independent dimensions and must not be
collapsed into one field.

### CanonStatus

```text
idea
draft
canon
deprecated
```

`idea` and `draft` represent material that is not yet canonical. `canon` is
active authoritative story material. `deprecated` is retained history that
must not enter an active episode context.

### ProductionStatus

```text
planned
outlined
drafting
revising
final
```

Production status describes the creation workflow and does not imply canon
status. A service may validate transitions in both dimensions independently.

## Core Data Model

The planned schema has the following table inventory. Migration ownership is
defined in the phase plans; table names and their conceptual boundaries are
stable across those plans.

```text
works

world_facts

timeline_events
timeline_event_participants
timeline_event_relations

characters
relationships
character_states

chapters
episodes
scenes
episode_characters
episode_world_facts
episode_timeline_events
episode_information

information_items
reader_disclosures
character_knowledge_events

canon_decisions
canon_decision_changes

drafts

schema_migrations
```

All story rows are scoped to the configured work even though normal tool input
does not expose a work selector. Cross-work reads and writes are rejected by
the service boundary. Foreign-key constraints are enabled for every database
connection.

Major mutable entities carry `version INTEGER NOT NULL DEFAULT 1`. Any update
that changes such an entity requires an `expected_version` value and must
reject a stale value with `VERSION_CONFLICT`.

## Historical Chronology / Narrative Disclosure

Three concepts are intentionally separate:

1. `timeline_events` record what happened in historical chronology.
2. `reader_disclosures` record when the reader learns an information item.
3. `character_knowledge_events` record when a character learns, suspects,
   believes, confirms, doubts, or rejects an information item.

For example, a state AI detecting a volcanic anomaly in 2104 is a
`timeline_event`. The reader learning that fact in episode 24 is a
`reader_disclosure`. The protagonist learning it in episode 37 is a
`character_knowledge_event`. None of these rows substitutes for another.

## Character State

`character_states` is a change-log of state changes, not an episode-by-episode
snapshot table. A character can have an initial state in episode 1, an
injured state in episode 12, and a recovered state in episode 18. The effective
state at episode 15 is resolved from the latest valid state change at or before
episode 15.

The future `character_state_get(character, episode)` service operation returns
the effective state for the requested episode, rather than returning a raw
database row selected without temporal resolution.

Knowledge is not stored as JSON in `character_states`. Character knowledge is
represented by `information_items` and `character_knowledge_events`.

## Character Knowledge

`information_items.truth_status` supports at least:

```text
true
false
uncertain
subjective
```

Character knowledge state supports:

```text
suspects
believes
knows
confirmed
doubts
rejected
```

An information item can be false, uncertain, or subjective while still being
known or believed by a character. Truth status and character knowledge state
must therefore remain independent.

## Canon Decisions

Canon change history is split between `canon_decisions` and
`canon_decision_changes`. One decision may describe changes to multiple
entities, such as changing a cooling-start date, a character age, and a world
fact statement in one canonical operation.

Canon changes and their decision record are written in the same transaction.
The reason is required for:

- `idea` or `draft` to `canon` transitions;
- content changes to canonical material;
- `canon` to `deprecated` transitions.

Ordinary edits to `idea` or `draft` material do not require a change reason.
Services reject a canon mutation that would violate these rules before any
partial write is committed.

## Optimistic Locking

The first version of a mutable entity is `1`. An update uses a compare-and-set
operation against the caller's `expected_version`. A matching value updates
the row and increments `version` atomically. A non-matching value produces a
structured `VERSION_CONFLICT` error and leaves the row unchanged.

The service layer owns the policy and transaction boundary; the repository
provides the conditional SQL operation and affected-row result. Silent
overwrite is forbidden.

## Search Strategy

Search is a read operation over the canonical SQLite database. Exact identity
and relationship lookups use ordinary indexed predicates. Timeline range
operations use chronology fields and bounded result ordering. Text search is
introduced by `002_search.sql` and must support the Japanese text search
baseline described in the Phase 1 plan.

The search implementation must be demonstrated by focused tests for Japanese
terms, empty queries, stable ordering, and work scoping before it is exposed by
MCP tools. Search indexes and derived search structures are rebuildable from
canonical rows; they do not become a second source of truth.

## MCP Tool Surface

MCP tools return structured JSON objects with stable field names and structured
errors. The tool layer delegates to services and does not expose database
connection objects, SQL, or arbitrary table operations.

### Phase 1 tools

```text
work_get
work_update

world_fact_create
world_fact_update
world_fact_get
world_fact_search

timeline_event_create
timeline_event_update
timeline_event_get
timeline_event_search
timeline_range
timeline_move
timeline_relation_create

character_create
character_update
character_get
character_search

relationship_create
relationship_update
relationship_search

canon_status_set
canon_decision_get
canon_decision_search
```

### Phase 2 tools

```text
chapter_create
chapter_update
chapter_reorder
chapter_list

episode_create
episode_update
episode_get
episode_reorder
episode_list

scene_create
scene_update
scene_get
scene_reorder
scene_list

episode_reference_add
episode_reference_remove
episode_reference_list

character_state_set
character_state_get
character_state_history

information_create
information_update
information_get
information_search

reader_disclosure_set
character_knowledge_set
character_knowledge_get
```

### Phase 3 tools

```text
episode_outline_get
episode_context
episode_draft_get
episode_draft_save
episode_draft_history
```

The database schema and MCP surface are not one-to-one. For example, the four
episode reference tables can be operated through the three
`episode_reference_*` tools.

## episode_context

`episode_context` is the principal Phase 3 read operation for safe authoring.
Its structured result contains:

```text
episode
scenes

participants[]
  profile
  effective_state
  effective_relationships
  known_information

world_facts[]
timeline_events[]

reader_context
  known_before_episode[]
  reveal_this_episode[]

protected_information_guards[]

recent_context
  previous_episode_summaries[]
  previous_draft_tail

foreshadowing_notes[]

context_meta
```

The initial fixed bounds are:

```text
previous_episode_summaries = 2
previous_draft_tail_chars = 4000
world_facts_max = 30
timeline_events_max = 30
information_items_max = 50
```

Phase 1–3 callers cannot replace these bounds with unbounded values.

The builder includes only data valid for the requested episode and configured
work. It excludes future episode data, future character states, future
character knowledge, future reader disclosures, deprecated canon, and data
belonging to another work. If future information is relevant as an authoring
constraint, the result may contain an `authoring_guard` describing the guard,
but must not return the secret's protected body.

## Error Model

Errors are structured JSON with a stable machine-readable code, a concise
message, and field or entity details when they are safe to expose. The initial
error categories are:

- `VALIDATION_ERROR` for malformed or domain-invalid input;
- `NOT_FOUND` for a missing entity inside the configured work;
- `WORK_SCOPE_ERROR` for a cross-work access attempt;
- `VERSION_CONFLICT` for a stale optimistic-lock version;
- `CANON_REASON_REQUIRED` when a protected canon transition lacks a reason;
- `CANON_POLICY_ERROR` for a forbidden canon mutation;
- `FUTURE_DATA_FORBIDDEN` when a context request would cross its episode bound;
- `DEPRECATED_CANON_FORBIDDEN` when deprecated canon is requested as active;
- `TRANSACTION_ERROR` when a transaction cannot be completed safely.

Errors must not disclose protected future information or silently repair invalid
source data. A failed transaction leaves all affected canonical rows unchanged.

## SQLite Defaults

Every connection applies at least:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

Migrations are explicit SQL files and are recorded in `schema_migrations`.
Once applied, a migration file is immutable. The fixed migration sequence is:

```text
001_initial.sql   Phase 1 core schema
002_search.sql    FTS and search support
003_narrative.sql Chapter, Episode, Scene, Character State, Information, and Disclosure
004_drafts.sql    append-only Draft revisions
```

Ordinary MCP startup never creates a work implicitly. A future Phase 1
`novel-init --db ./data/story.db --title "2126"` command performs explicit
database and work initialization; this command is planned but is not part of
the initial repository commit.

## Phase Responsibilities

### Phase 1

Phase 1 establishes the database lifecycle, work metadata, world facts,
historical timeline, characters, directional relationships, canon decisions,
Japanese text search baseline, and stdio tool surface.

### Phase 2

Phase 2 adds chapters, episodes, scenes, atomic ordering, temporal character
state resolution, information items, reader disclosures, character knowledge,
and episode references.

### Phase 3

Phase 3 adds append-only draft revisions, episode outline retrieval, bounded
episode context, leakage hardening, and the real-writing acceptance gate.

The corresponding plans specify files, interfaces, failing tests, execution,
implementation steps, validation, and independent commits for each task.

## Acceptance Criteria

The architecture is accepted when the future implementation and repository
history demonstrate all of the following:

1. The repository keeps `MCP/`, `data/`, and `docs/` as root-level concerns.
2. All implementation paths are under `MCP/`.
3. The four migration numbers and responsibilities remain consistent.
4. One MCP instance resolves exactly one configured story database.
5. Historical chronology, reader disclosure, and character knowledge remain
   separate concepts and tables.
6. Canon status and production status remain separate.
7. Character state is stored as changes and resolved effectively by episode.
8. Draft revisions are append-only.
9. Mutable entity updates require optimistic locking.
10. `episode_context` enforces fixed bounds and rejects future, deprecated, or
    cross-work leakage.
11. Service, repository, and MCP tool responsibilities remain separated.
12. SQLite remains the canonical source of truth.
13. Structured tool output and structured error codes are stable and testable.

## Project Shape

```text
NovelProduction/
├─ MCP/
│  ├─ migrations/
│  ├─ src/
│  │  └─ novel_mcp/
│  ├─ tests/
│  ├─ pyproject.toml
│  └─ README.md
├─ data/
├─ docs/
│  └─ superpowers/
│     ├─ specs/
│     └─ plans/
├─ .gitignore
└─ README.md
```

The `WEB/` directory is intentionally not created until a web component has a
separate approved scope.

## Deferred Features

The following are deliberately excluded from this design cycle:

- WEB UI and browser-facing workflows;
- MCP widgets and ChatGPT Apps UI;
- vector databases and embeddings;
- ORM abstractions;
- external search services;
- Docker and CI/CD configuration;
- release and deployment automation;
- automatic work creation at MCP startup;
- generated story databases or sample story content;
- implementation of Phase 1–3 runtime code.

These exclusions keep the initial commit limited to repository structure,
architecture documentation, implementation plans, and project metadata.

## Implementation Detail

The following choices are intentionally implementation-level and are governed
by the plans rather than by additional product behavior:

- Python package layout uses `MCP/src/novel_mcp`.
- SQLite access uses standard-library `sqlite3` connections created by the
  database lifecycle boundary.
- The official Python MCP SDK v2 is declared as `mcp>=2.0,<3.0` without a
  patch-level pin in the bootstrap metadata.
- The stdio adapter is the first transport; tool payloads are structured JSON.
- Each task adds focused tests before the smallest implementation needed to
  satisfy them and ends with an independently reviewable commit.

Implementation details may refine internal modules and SQL indexes, but they
must not alter the status values, table inventory, migration sequence,
layering, temporal boundaries, or leakage rules defined above.
