# Novel Production MCP Design Specification

**Status:** Phase 1 and Phase 2 implemented and merged; Phase 3 implementation contract approved

**Date:** 2026-08-26

## Purpose

Novel Production MCP is a tool-only MCP component for maintaining a structured
novel-production database. The component will provide bounded, transactional
operations over story canon, historical chronology, narrative structure,
character state, information disclosure, and append-only episode drafts.

This specification defines the Phase 1–3 architecture and the invariants that
implementation must preserve. Phase 1 and Phase 2 are implemented and merged
on `main` at `0a10faf6b8c1ba9c838e6aea1cd0ab84cdb51ef6`. This document fixes
the Phase 2 contract and the approved Phase 3 implementation contract. Phase 3
is the current implementation scope; Phase 4 and later runtime features
remain deferred.

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
- Production deployment, production CI/CD, Docker, release management, and hosting.
- ORM, vector search, embeddings, or an external search service.
- Automatic story creation during ordinary MCP startup.
- A generated `story.db` in the repository.
- Any live writing workflow before the Phase 3 acceptance gate.

## Development Constraints

Phase 1 uses a reproducible repository development foundation in addition to
the runtime architecture:

- `MCP/pyproject.toml` and `MCP/uv.lock` are the authoritative Python
  dependency files. `uv sync --all-groups` is the supported environment setup.
- `.python-version` contains the concrete Python version used by CI. Ruff is
  the lint and formatter, mypy is strict by default, pytest/pytest-cov provide
  the test and coverage baseline, and pre-commit runs lightweight checks.
- Repository text files use UTF-8, LF endings, final newlines, and no trailing
  whitespace. Standard-library `logging` may record diagnostic events, but it
  must not record novel prose, secret settings, episode context, private notes,
  or draft bodies.
- Production Python modules under `MCP/src/**/*.py` must not exceed 600 lines
  or 40 KiB. Test modules under `MCP/tests/**/*.py` must not exceed 800 lines.
  Generated files, `uv.lock`, migration SQL, fixtures, snapshots, and vendored
  code are exempt. A small automated source-size check enforces the hard
  limits; SHOULD thresholds are advisory.
- Repository GitHub Actions checks run on pushes and pull requests. They cover
  dependency synchronization, Ruff, mypy, pytest, and the source-size gate.
- Phase 1 and Phase 2 are implemented and merged on `main` at
  `0a10faf6b8c1ba9c838e6aea1cd0ab84cdb51ef6`. `001_initial.sql`,
  `002_search.sql`, and `003_narrative.sql` are immutable for Phase 3. The
  only migration added by Phase 3 is `004_drafts.sql`; `005_*` and later
  migrations are forbidden.
- Phase 3 is implemented sequentially by Codex Luna in the approved worktree.
  Subagent dispatch and model escalation are forbidden. Architecture and
  product decisions follow this approved contract; implementation may not
  silently simplify or redesign it.

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

### Phase 1 normalized core fields

The Phase 1 migrations implement the following normalized fields. These are
the canonical SQLite columns and corresponding service/MCP payload names;
legacy compatibility properties may exist on Python records but are not
additional sources of truth.

`works` contains:

```text
id, slug, working_title, genre, premise, themes_json, description,
production_status, version, created_at, updated_at
```

`production_status` is constrained to `planned`, `outlined`, `drafting`,
`revising`, or `final`. `themes_json` is valid JSON at both the service and
SQLite boundaries. `slug` remains the stable internal work identifier; the
working title and other metadata fields are the normalized authoring metadata
exposed by the Phase 1 work tools.

`world_facts` contains:

```text
id, work_id, topic_key, category, title, statement, details_json,
valid_from, valid_to, canon_status, importance, version, created_at, updated_at
```

`topic_key` is not unique within a work. Multiple rows may represent the same
topic at different validity ranges, and `(work_id, topic_key, id)` is indexed
for deterministic lookup without making the derived search index canonical.

`characters` contains:

```text
id, work_id, character_key, display_name, entity_type, description,
birth_date, death_date, physical_description, occupation, core_beliefs,
goals, fears, personality, speech_style, ai_attitude,
genetic_modification_attitude, private_notes, profile_json, canon_status,
version, created_at, updated_at
```

`entity_type` is constrained to `human`, `ai`, or `organization`.

`timeline_events` contains:

```text
id, work_id, event_key, time_start, time_end, date_precision, date_display,
title, description, category, location_world_fact_id, cause_summary,
consequence_summary, canon_status, importance, version, created_at, updated_at
```

`time_start` and `time_end` are nullable internal range endpoints. The
human-facing `date_display` is independent. `date_precision` is constrained to
`unknown`, `year`, `season`, `month`, or `day`, allowing values such as
`2104年`, `2104年春頃`, `2104年3月頃`, and `正確な日付不明` without treating
the display string as a sort key.

`timeline_event_participants` contains `event_id`, `character_id`, and `role`;
`character_id` is a foreign key to `characters`, so human, AI, and
organization participants share one integrity path. A free-text participant
label is not canonical.

`relationships` contains:

```text
id, work_id, source_character_id, target_character_id, relationship_type,
description, canon_status, valid_from_episode_id, valid_to_episode_id,
version, created_at, updated_at
```

Relationships and timeline locations use SQLite foreign keys, while services
also verify that all referenced rows belong to the configured work. The Phase 1
unique constraint on `(source_character_id, target_character_id,
relationship_type)` is rebuilt by `003_narrative.sql` so multiple non-overlapping
narrative intervals can coexist. `valid_from_episode_id` is inclusive and
`valid_to_episode_id` is exclusive; NULL means the narrative beginning or end.

### Phase 2 implementation contract

`003_narrative.sql` is the only migration added by Phase 2. It creates
`chapters`, `episodes`, `scenes`, `character_states`, `information_items`,
`reader_disclosures`, `character_knowledge_events`,
`episode_characters`, `episode_world_facts`, `episode_timeline_events`, and
`episode_information`. It also safely rebuilds `relationships` and the
`canon_decision_changes` CHECK constraint while preserving all existing row
IDs, work IDs, content, canon status, versions, and timestamps. Existing
relationship rows receive NULL temporal boundaries. No draft table or Phase 3
tool is part of this migration.

Chapters, episodes, and scenes have 1-based positions and append at
`MAX(position) + 1`. Their minimum fields are:

```text
chapters: id, work_id, position, title, summary, purpose, canon_status,
          production_status, version, created_at, updated_at
episodes: id, work_id, chapter_id, position, title, summary, purpose,
          foreshadowing_notes_json, canon_status, production_status, version,
          created_at, updated_at
scenes:   id, work_id, episode_id, position, title, summary, purpose,
          canon_status, production_status, version, created_at, updated_at
```

`canon_status` is `idea|draft|canon|deprecated` and `production_status` is
`planned|outlined|drafting|revising|final`. Chapter and episode positions
are unique within their work/parent; scene positions are unique within an
episode. Reorder is one transaction: the moved row requires
`expected_version`, collision-free temporary positions outside the live range
avoid unique collisions, and
every moved or shifted row increments its version. A no-op does not increment
versions, and a failed reorder rolls back all positions and versions.

`character_states` is a change-log, not a snapshot. It stores physical and
emotional state, `beliefs_json`, `location_world_fact_id`, and `state_json`,
but never character knowledge, known information, or reader disclosure.
`beliefs_json` and `state_json` must be valid JSON. The canonical change row
for a character and episode is unique. Creation accepts
`expected_version = None`; correction of an existing same-episode row
requires `expected_version`. Effective state uses chapter position followed by
episode position and never compares episode IDs.

`information_items` stores `statement`, `truth_status`, `authoring_guard`,
`notes_json`, `canon_status`, `importance`, and version/timestamps.
`truth_status` is `true|false|uncertain|subjective`, `importance` is a
non-negative integer, and `notes_json` is valid JSON. `authoring_guard` is
metadata about a protected statement and does not move into character state.
`reader_disclosures` has one canonical first-disclosure boundary per item;
moving that boundary is an optimistic-locked transaction. For a target episode,
known-before means disclosure narrative position `< target`, and reveal-this-
episode means position `== target`.

`character_knowledge_events` is independent from reader disclosure and stores
the character, information item, episode, `knowledge_state`, note, and version.
Knowledge state is `suspects|believes|knows|confirmed|doubts|rejected`.
Truth and knowledge are never collapsed: a false item may be believed. Effective
knowledge and its source event are resolved by chapter/episode narrative order,
excluding future events. The structured result includes the effective state,
effective event episode, and information item.

Episode references use four separate link tables and one MCP tool family:
`episode_reference_add`, `episode_reference_remove`, and
`episode_reference_list`. Supported types are `character`, `world_fact`,
`timeline_event`, and `information`; character role defaults to
`participant` and is a bounded string. Services verify that episode, target,
and configured work agree. Removal is idempotent and returns `removed: false`
for an absent link. Reference tables never substitute for disclosure
boundaries. Cross-work links are rejected.

Explicit authoring/admin reads such as `information_get`,
`information_search`, and `character_state_history` may return future or
deprecated rows because they are not narrative-boundary context reads. Future
and deprecated filtering applies to effective state, effective knowledge,
reader-boundary queries, effective relationships, and the future Phase 3
`episode_context`; `episode_context` itself is not implemented in Phase 2.

The Phase 2 MCP surface is exactly 27 tools, added to the 23 Phase 1 tools for
50 total. Every Phase 2 description begins with `Use this when ...`; schemas
expose enum and bound constraints while services remain authoritative. Read
tools use `readOnlyHint=true`, `destructiveHint=false`, and
`openWorldHint=false`. Create uses read-only false and destructive false;
update/reorder/set use read-only false and open-world false;
`episode_reference_remove` additionally uses `destructiveHint=true`.

All Phase 1 canon fields use a SQLite `CHECK` for
`idea|draft|canon|deprecated`; all mutable entity versions use
`CHECK(version >= 1)`. Episode-dependent relationship validity fields remain
Phase 2.

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
operations use internal chronology endpoints and bounded overlap ordering. Text
search prefers an available SQLite FTS5 trigram strategy; when that capability
is unavailable, the repository uses parameterized, escaped `LIKE` fallback.
The selected strategy is diagnostically observable. FTS/index rows are
rebuildable derived data and never become a second source of truth.

The search implementation must be demonstrated by focused tests for Japanese
terms, empty queries, stable ordering, and work scoping before it is exposed by
MCP tools. Search indexes and derived search structures are rebuildable from
canonical rows; they do not become a second source of truth.

## MCP Tool Surface

MCP tools return structured JSON objects with stable field names and structured
errors. The tool layer delegates to services and does not expose database
connection objects, SQL, or arbitrary table operations. All 23 Phase 1 tools
have explicit `Use this when ...` descriptions. Their generated JSON Schemas
expose bounds and enum values where the contract defines them, while service
validation remains authoritative.

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
    physical_state
    emotional_state
    beliefs
    location_world_fact_id
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

Noncritical `known_before_episode` information candidates are relevance-bound
to explicit current-episode `episode_information` references and effective
knowledge of current participants. Phase 3 performs no vector or whole-database
semantic scan for those candidates. This bound does not apply to canonical
current reveals: every active information item whose `reader_disclosures`
boundary targets the current episode is relevant to
`reader_context.reveal_this_episode` even when it has no episode reference and
no participant knowledge. Current reveals are deduplicated, exclude deprecated
information, are critical data, and are not truncated by
`information_items_max`.

Effective character state is the latest state change at or before the target
according to chapter/episode narrative order, never episode ID ordering. The
Phase 3 safe projection parses `character_states.beliefs_json` and returns it
as structured `beliefs` together with physical/emotional state and location.
Future beliefs are excluded and raw `state_json` is not exposed.

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
Phase 1 is merged and its migration bytes are immutable. The fixed migration
sequence is:

```text
001_initial.sql   Phase 1 core schema
002_search.sql    FTS and search support
003_narrative.sql Chapter, Episode, Scene, Character State, Information, and Disclosure
004_drafts.sql    append-only Draft revisions
```

Ordinary MCP startup never creates a work implicitly. A future Phase 1
`novel-init --db ./data/story.db --working-title "2126"` command performs explicit
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

## Phase 3 Implementation Contract

Phase 3 implementation starts from merged Phase 2 at
`0a10faf6b8c1ba9c838e6aea1cd0ab84cdb51ef6`. The three existing migrations are
byte-for-byte immutable. `004_drafts.sql` is the only new migration, and no
`005_*` migration may be created.

### Append-only episode drafts

`drafts` contains `id`, `work_id`, `episode_id`, `revision`,
`parent_draft_id`, `body`, `source_agent`, `change_summary`, `content_hash`,
and `created_at`. It enforces positive revisions, unique
`(episode_id, revision)`, non-empty bodies, a 64-character hash, configured
work/episode composite integrity, and same-episode parent lineage. Database
`BEFORE UPDATE` and `BEFORE DELETE` triggers abort all in-place changes.

Draft save preserves the exact input string, including leading/trailing
whitespace and newlines. `content_hash` is lower-case SHA-256 over the exact
UTF-8 body bytes. A save runs in a `BEGIN IMMEDIATE`-equivalent transaction,
checks the latest revision and `expected_parent_draft_id`, allocates the next
revision, and inserts one row. The first revision has a NULL parent; every
later revision must point to the current latest row. A stale parent returns
`VERSION_CONFLICT` without a partial write. Draft history is metadata-only;
full bodies are returned only by an exact/latest draft get.

### Safe outline and context projections

`episode_outline_get` and `episode_context` use explicit projections rather
than raw database row dumps. Participant profiles may contain only `id`,
`character_key`, `display_name`, `entity_type`, `description`, `birth_date`,
`physical_description`, `occupation`, `core_beliefs`, `goals`, `fears`,
`personality`, `speech_style`, `ai_attitude`,
`genetic_modification_attitude`, and `canon_status`. They must not expose
`private_notes`, `profile_json`, or `death_date`. World facts omit
`details_json`; timeline events are limited to the approved safe projection.

For noncritical `known_before_episode`, episode references are the relevance
boundary: candidates come from current `episode_information` references plus
effective knowledge of current participants. Phase 3 performs no vector or
whole-database semantic search for those candidates. Current reveals are the
explicit exception: an active `information_item` with a `reader_disclosures`
boundary at the target episode is canonical current-reveal relevance by itself,
requires neither an episode reference nor participant knowledge, and is
critical/non-truncated. Deprecated target episodes fail with
`DEPRECATED_CANON_FORBIDDEN`; deprecated referenced or current-reveal entities
are excluded. `idea`, `draft`, and `canon` remain distinct status values and
are not implicitly promoted.

Any narrative proposition that must not yet be disclosed to the reader is
stored in `information_items`. `character.private_notes`,
`character.profile_json`, and `world_fact.details_json` are not substitutes
for the normalized disclosure model. Narrative-boundary reads use
`information_items`, `reader_disclosures`, and
`character_knowledge_events` to decide what may be shown.

Information statements are governed by `reader_disclosures`: disclosures
before the target are `known_before_episode`, and disclosures at the target
are `reveal_this_episode`. Undisclosed or future information never exposes its
statement, notes, or other secret body, even when a character already knows
it. Such relevant items produce only a safe `protected_information_guards`
entry with IDs, reason, guard text, and reveal boundary positions. A stored
`authoring_guard` is used only when it does not contain the protected
statement; otherwise a generic safe guard is returned.

Effective participant state uses the latest `character_states` row at or before
the target by chapter/episode narrative order. Its safe Phase 3 projection
includes physical state, emotional state, structured `beliefs` parsed from
`beliefs_json`, and location. Future state and future beliefs are excluded;
raw `state_json` is not returned.

The context has fixed server-side limits: two previous episode summaries,
4000 characters of the previous episode's latest draft tail, 30 referenced
world facts, 30 referenced timeline events, and 50 distinct noncritical
reader-safe `known_before_episode` information items. Current episode data,
participants, scenes, all active current reveals, and safe guards are not
silently dropped by those limits. Selection and ordering are deterministic,
narrative order uses chapter and episode positions, and context metadata
reports limits, returned counts, omitted counts, and truncation flags without
secret text. Context assembly is strictly read-only and performs no mutation,
migration, auto-canon, auto-summary, or draft save.

### Phase 3 MCP surface and acceptance

Phase 3 adds exactly these five tools to the existing 23 Phase 1 and 27 Phase
2 tools, for exactly 55 tools total:

```text
episode_outline_get
episode_context
episode_draft_get
episode_draft_save
episode_draft_history
```

All five descriptions begin with `Use this when ...`. The four read tools use
`readOnlyHint=true`, `destructiveHint=false`, and `openWorldHint=false`.
`episode_draft_save` uses `readOnlyHint=false`,
`destructiveHint=false`, and `openWorldHint=false`. The handlers remain thin
and delegate to services through `phase3_tools.py`.

The internal real-writing acceptance gate records individual booleans for
migration order, append-only drafts, parent CAS, hash correctness, safe
outline, bounded/read-only context, all future/deprecated/cross-work/private
field leakage categories, guard presence, exact tool inventory, and
`writing_ready`. It is an active-probe gate: the qualification database seeds
hazardous sentinels for future episode/state/knowledge/disclosure,
deprecated and cross-work data, private fields, protected statements, and data
beyond every context bound before evaluating the corresponding invariant.
Missing hazardous source data cannot produce a vacuous PASS. Every reader-safe
statement returned by the probe must have a reader-disclosure boundary at or
before the target. `writing_ready` is true only when every required active
assertion is true; a process exit code alone is not evidence.

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
- Production Docker and CI/CD configuration;
- release and deployment automation;
- automatic work creation at MCP startup;
- generated story databases or sample story content;
- Phase 4 continuity checks, story-thread engines, automatic contradiction
  repair, automatic canon mutation/promotion, vector or graph databases,
  automatic prose or outline generation, web/widgets/Apps UI, Docker,
  deployment, production story data, and migrations after `004_drafts.sql`.
