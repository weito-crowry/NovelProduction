# NovelProduction Phase E — Structured Manuscript / Rich Authoring Design

Status: **Approved for implementation planning**

This document is the detailed source of truth for Phase E. It supersedes the
earlier Phase E structured-draft details in
[`2026-08-28-novelproduction-webui-architecture-design.md`](2026-08-28-novelproduction-webui-architecture-design.md).
Phase E is documented here only; this document does not authorize E1
implementation, migration 005 creation, or the Final Cutover.

## 1. Phase E purpose

Phase E retires draft management based on a single `body TEXT` value and makes
the structured Canonical Document the only source of truth for manuscript
content.

The goals are to:

- let LLM clients handle prose and block metadata together;
- preserve speaker, scene, emotions, and arbitrary metadata across revisions;
- provide high-quality novel reading in the WEBUI;
- support the minimum necessary human editing in the WEBUI;
- retain append-only revision history;
- prevent silent overwrite from stale saves;
- avoid excessive MCP call counts and token volume;
- add arbitrary annotations without changing the CORE schema;
- allow future Document Schema and export-format additions;
- avoid making CORE enforce story plausibility; and
- keep the WEBUI Read-first with a thin editor.

## 2. Persistent representation

The only persisted manuscript content is `document_json`.

The following are not persisted:

- `body`;
- `content_hash`;
- `document_hash`;
- derived HTML;
- derived text; and
- a `document_schema_version` database column.

The Canonical Document is the only complete, self-contained representation.
Restricted Authoring HTML is an editing interchange format and is not a full
replacement for the Canonical Document.

## 3. Responsibility

CORE owns:

- the Document Schema;
- structural validation;
- normalization;
- version dispatch;
- Restricted HTML parsing and serialization;
- block identity reconciliation;
- metadata semantics;
- projections;
- export;
- draft authoring;
- CAS; and
- restore.

SQLite owns JSON syntax validity, foreign keys, revision constraints, and
append-only persistence.

API owns the HTTP contract, CORE error mapping, conflict responses, and the
export endpoint.

MCP is a stateless API adapter and does not reimplement Document semantics.

WEBUI owns presentation, interaction, the TipTap adapter, and Read/Edit UX.

## 4. Creative validation philosophy

Document validation protects structure only. It does not enforce story
validation such as:

- whether a speaker is registered as an episode participant;
- whether a character should be present in the scene;
- whether a character should know information;
- whether prose is narratively natural; or
- whether continuity is natural.

The governing principle is: **absence of evidence is not contradiction**.

## 5. Canonical Document Schema v1

The document envelope is:

```json
{
  "schema_version": 1,
  "type": "novel_document",
  "blocks": []
}
```

`blocks: []` is valid.

A block is shaped as follows:

```json
{
  "id": "blk_<uuid4hex>",
  "type": "dialogue",
  "html": "「急いで！」",
  "attrs": {
    "scene_id": 3,
    "speaker_character_id": 12
  },
  "annotations": {
    "emotions": ["焦り"],
    "snack-count": 3
  }
}
```

Blocks are ordered and flat. They are not represented as a nested Scene tree.

## 6. Block types

Phase E supports these semantic block types:

- `narration`;
- `dialogue`;
- `thought`;
- `description`;
- `quote`;
- `heading`;
- `separator`; and
- `note`.

The type is semantic classification only. A `dialogue` block does not cause
Japanese quotation marks or other symbols to be generated automatically.

## 7. Block HTML

`html` is a Restricted Inline HTML fragment and does not include the outer
block tag.

The Phase E inline whitelist is:

- `<strong>`;
- `<em>`;
- `<em data-emphasis="dot">`;
- `<ruby>`;
- `<rt>`; and
- `<br>`.

Links, arbitrary spans, styles, classes, images, tables, lists, scripts, and
arbitrary HTML are forbidden. Each block is a separate paragraph; `<br>` is a
line break within one block.

## 8. Attributes

Attributes are strict structural metadata. Phase E supports only:

- `scene_id`;
- `speaker_character_id`; and
- `heading_level`.

Unknown attributes are validation errors. When a normal save newly sets or
changes `scene_id`, the scene must exist in the episode. When a normal save
newly sets or changes `speaker_character_id`, the character must exist in the
same work. Episode participant registration is not required. `heading_level`
must be an integer from 1 through 3.

## 9. Annotations

Annotations are extensible metadata. A Canonical annotation key is any
non-empty string. Values are standard JSON values: `null`, booleans, strings,
finite numbers, arrays, or objects. NaN and Infinity are forbidden.

Unknown annotations must not be silently dropped, and block type does not
restrict annotation use.

The formally recognized annotation is `emotions: string[]`. `emotions`
represents block-level expressive nuance and does not update
`character_states.emotional_state`.

## 10. Block identity

The formal block ID shape is `blk_<uuid4 hex>`. CORE generates these IDs. They
are opaque identities and must not encode episode, revision, position, or
scene semantics.

An ID present in the parent revision identifies the same logical block. An
input without an ID describes a new block, for which CORE issues a formal ID.
An ID supplied that is absent from the parent is treated as a same-request
correlation key and is converted to a formal ID on save.

The save response may include an ID map:

```json
{
  "id_map": {
    "new-dialogue-1": "blk_..."
  }
}
```

All non-empty IDs in one HTML input must be unique. Duplicate known or
unknown IDs are validation errors. A `metadata_updates` entry referring to an
ID absent from both the parent and the same-request HTML is a validation
error.

## 11. Full HTML snapshot semantics

An HTML edit is a new ordered block snapshot of the entire episode manuscript.
If the parent is `A B C` and the submitted snapshot is `A C`, the new revision
is `A C`; `B` is deleted.

Omitting metadata while retaining an existing block inherits that block's
parent metadata. Omitting the block itself deletes it.

## 12. Block ID reuse, split, and merge

Normal authoring must not reuse a deleted historical ID for a new logical
block. Restore may reintroduce historical IDs because it restores a historical
Canonical snapshot.

For a split, the retained first portion keeps the original ID, the new portion
receives a new ID, and the new portion receives no automatic metadata
inheritance.

Phase E has no metadata-aware dedicated merge. A normal editor merge keeps A's
ID and metadata, appends B's prose to A, deletes B, and discards B's metadata.

## 13. Canonical normalization

Normalization must provide, at minimum:

- deterministic JSON serialization;
- deterministic object representation;
- `\n` line endings;
- omission of null optional attributes;
- permission to retain `annotations: {}`;
- deterministic serialization of allowed inline HTML;
- preservation of block order; and
- no arbitrary collapse of meaningful whitespace.

## 14. Schema versioning

`schema_version` exists only inside the Canonical Document. Phase E implements
version 1 only.

Reads dispatch by `schema_version` and then perform structural validation.
Unknown versions fail. Past revisions are never rewritten for schema upgrade
purposes. Boundaries for a future v2 or later version may exist, but no fake
future implementation is introduced.

## 15. Two-level validation

Structural validation applies to both reads and writes and does not depend on
current database state. It covers, for example:

- JSON shape;
- schema version;
- document type;
- block ID shape;
- duplicate canonical IDs;
- block type;
- HTML;
- attribute names and types;
- heading consistency; and
- annotation JSON validity.

Live reference validation applies only to a normal save and only to newly set
or changed `scene_id` and `speaker_character_id` values. Attributes inherited
unchanged from the parent are not revalidated.

Historical revision GET performs structural validation only. Restore performs
historical structural validation only and does not revalidate live references.
Consequently, changes to the current scene or character structure cannot make
a past revision unreadable.

## 16. Stored corruption

Invalid caller input is reported as `DOCUMENT_SCHEMA_ERROR` and maps to HTTP
422.

A stored Document that is structurally invalid is reported as
`DOCUMENT_STORAGE_ERROR` and maps to an HTTP 500-class response.

Stored corruption is never automatically repaired.

## 17. Restricted Authoring HTML

Block mapping is:

- `<p>` -> narration by default for a new block;
- `<p data-np-type="dialogue">`, `thought`, `description`, or `note` -> the
  corresponding block type;
- `<blockquote>` -> `quote`;
- `<h1>`, `<h2>`, or `<h3>` -> `heading` levels 1, 2, or 3; and
- `<hr>` -> `separator`.

## 18. Metadata namespaces

`id` is the block identity namespace. `data-np-*` is reserved for structural
and control metadata. Phase E defines:

- `data-np-type`;
- `data-np-scene-id`;
- `data-np-speaker-id`; and
- `data-np-remove-annotations`.

Unknown `data-np-*` attributes are validation errors.

HTML annotations use `data-ann-<lowercase-ascii-kebab-case>`. The Canonical
annotation namespace is broader. Unknown HTML annotation values are strings;
their types are never guessed. For example,
`data-ann-snack-count="3"` becomes the Canonical string `"3"`.

The recognized emotions codec is:

```html
data-ann-emotions='["焦り"]'
```

## 19. Complex annotations

Unknown complex JSON is not forcibly stringified into Restricted HTML. It is
preserved in the Canonical Document. An `all` HTML projection may omit a
complex annotation when it cannot safely round-trip it.

## 20. Annotation projection

For `format=html`, annotation projection supports `none`, `selected`, and
`all`. Even `all` includes only HTML-safe annotations. To inspect all
Canonical metadata, clients use `format=document`.

## 21. Authoring preservation

Authoring HTML is not a self-contained full document. For parent-relative
editing round trips that use known block IDs, metadata not projected into the
HTML is inherited from the parent. Authoring HTML includes `note` blocks.

## 22. Metadata inheritance

For attributes, omission means inherit, an explicit value means set/update,
JSON `null` means clear, and an empty HTML structural attribute means clear.

For annotations, omission means inherit, an explicit value means set/replace,
and an empty string is a valid value. Deletion must be explicit.

HTML annotation removal uses:

```html
data-np-remove-annotations='["foo","bar"]'
```

## 23. Type semantics

For an existing `<p id="known">`, omission of `data-np-type` inherits the
parent type. For a new `<p>`, omission means `narration`. An explicit known
type changes the type; an empty type is a validation error.

The following tags force their structural type:

- `<blockquote>` -> `quote`;
- `<h1>`, `<h2>`, and `<h3>` -> `heading`; and
- `<hr>` -> `separator`.

## 24. `metadata_updates`

The existing `episode_draft_save` operation gains a batch JSON
`metadata_updates` interface so multiple blocks can be changed in one
request.

For attributes, omission means inherit, a value sets the attribute, `null`
clears it, and an unknown attribute is an error.

For annotations, omission means inherit, arbitrary JSON sets or replaces the
value, JSON `null` is a valid value, `remove_annotations` deletes keys, and
removing a nonexistent key is a no-op. HTML and `metadata_updates` may be used
together, and same-request correlation IDs may be referenced.

## 25. Same-request conflict

If HTML and `metadata_updates` explicitly set the same block field, equal
values after normalization are accepted and unequal values are validation
errors. Setting and removing the same field in one request is also a
validation error. Precedence is never used to resolve these conflicts.

## 26. Initial draft

Revision 1 accepts exactly one of `plain_text` or `html`. An empty string is
valid, and `plain_text=""` or `html=""` creates an empty Document. Omitted
parameters are distinct from empty strings.

## 27. Plain importer

The plain-text importer trims surrounding excess blank lines, splits blocks on
runs of blank lines, and converts a single newline to `<br>`. Every imported
block is `narration`. The importer performs no dialogue, heading, separator,
or AI classification inference.

After a structured revision is created, subsequent edits do not use
`plain_text`.

## 28. Normal save

For revision 2 and later, a save must include at least one of `html` or
`metadata_updates`, and `expected_parent_draft_id` is required. `html=""`
means that all blocks are deleted.

## 29. Restore

`restore_revision` is mutually exclusive with `plain_text`, `html`, and
`metadata_updates`. It requires `expected_parent_draft_id`, directly copies
the historical Canonical Document, does not round-trip through HTML, and does
not revalidate live references.

## 30. Save response

The save response does not echo the full HTML. It contains at least:

- `id`;
- `revision`;
- `parent_draft_id`; and
- `id_map`.

## 31. CAS

When there is no initial latest revision, the expected parent is null or
omitted. When a latest revision exists, `expected_parent_draft_id` is required.
A stale parent produces `VERSION_CONFLICT` and makes no database change.
Omitting the expected parent never implicitly adopts the latest revision.

## 32. History

History is metadata-only and contains at least:

- `id`;
- `episode_id`;
- `revision`;
- `parent_draft_id`;
- `source_agent`;
- `change_summary`; and
- `created_at`.

Past content is obtained with `episode_draft_get(revision=N)`. Restore is a new
append, not a mutation of the past revision.

## 33. Migration 005

Migrations 001 through 004 are unchanged. Migration 005 drops and recreates
the old drafts from migration 004, with no data migration or backfill.

The new drafts concept contains:

- `id`;
- `work_id`;
- `episode_id`;
- `revision`;
- `parent_draft_id`;
- `document_json`;
- `source_agent`;
- `change_summary`; and
- `created_at`.

SQLite requires at least:

```sql
document_json TEXT NOT NULL CHECK(json_valid(document_json))
```

It also requires foreign keys, revision uniqueness, parent references, and
append-only triggers. Document semantic validation is not duplicated in SQL.

## 34. Draft GET formats

`format=html` is the default and returns Restricted Authoring HTML.
`format=web` returns CORE-generated WEB Read semantic HTML.
`format=document` returns Canonical Document JSON. `document` is not a public
write format.

## 35. Projection identity

Authoring HTML includes block IDs, structural attributes, requested/projectable
annotations, and `note` blocks.

WEB Read HTML includes block IDs and semantic rendering, while editing metadata
is normally omitted and `note` is normally hidden.

Context HTML omits block IDs, retains type/scene/speaker, normally omits
annotations, and omits `note`.

Export omits block IDs, metadata, and `note`.

## 36. WEBUI edit annotations

The normal TipTap projection uses selected annotations such as
`selected(["emotions"])`; it does not pass all unknown annotations into
TipTap. Raw metadata is inspected with `format=document`.

## 37. MCP annotations

MCP supports `none`, `selected`, and `all`. Clients that need to inspect all
complex metadata use `format=document`.

## 38. `episode_context`

The old plain-text `recent_context.previous_draft_tail` is removed. The new
concept is `recent_context.previous_draft_context_html`.

Context HTML has no block IDs, retains type, scene, and speaker, and includes
ruby and inline semantics. It normally omits annotations and never includes
`note`.

## 39. Context truncation

Context targets approximately 4,000 base visible-text characters. HTML markup
is outside the budget. In
`<ruby>東京<rt>とうきょう</rt></ruby>`, the budget counts the two base
characters in `東京`, not the markup or reading.

Blocks are selected from the end, a block is never cut in the middle, and a
single block longer than 4,000 characters is included whole. The final order
is the original order. Context metadata names must describe visible-text
characters rather than HTML length.

## 40. WEBUI Read

Opening an episode starts in Read mode. Phase E uses horizontal writing only,
Japanese Mincho for the body, Gothic for the UI, a centered desktop layout,
approximately 40–50em readable width, readable line height, paragraph
spacing, and responsive mobile margins. There is no font selector. Vertical
writing is future work.

Formal rendering includes ruby, Japanese emphasis dots, headings, separators,
quotes, and paragraphs.

## 41. Notes

In Read mode, notes are hidden by default and exposed by a “Show production
notes” toggle. In Edit mode, notes are always visible. Context and Export
exclude notes.

## 42. WEBUI raw metadata visibility

The selected-block detail view exposes type, scene, speaker, heading level,
emotions, and projectable unknown annotations. It also provides a raw
annotations JSON viewer, including read-only complex unknown JSON, and a
read-only episode-level Raw Document JSON viewer.

## 43. WEBUI Edit

The flow is Read -> Edit -> TipTap, with Save and Cancel actions. A successful
save returns to Read mode. There is no autosave.

Dirty state includes prose, type, scene, speaker, heading, emotions, and
formatting. Selection, history, raw-view toggle, and note-view toggle are not
dirty state. Navigating away from dirty edits produces a warning.

## 44. WEBUI editable metadata

Phase E permits editing type, scene, speaker, heading level, and emotions.
Unknown annotations are read-only; there is no generic arbitrary JSON editor.
Right-pane edits update TipTap attributes and do not create a second Canonical
metadata state.

## 45. Formatting controls

The primary controls are Ruby, Japanese emphasis dots, Heading, Separator, and
Note. The schema and parser support bold and italic, but those controls need
not be prominent in the UI.

Ruby supports adding a reading, editing a reading, and removing the reading
while preserving the base text. Automatic ruby generation and dictionaries
are future work. Separator is inserted as an independent structural block.

## 46. Export

Publication export is WEBUI/API-only; MCP receives no publication export tool.
CORE exposes a format-dispatch exporter boundary. Phase E implements `narou`.
Kakuyomu, Markdown, plain, Aozora, and other formats are future additions.

Exporters read the Canonical Document directly. The two-stage
Document -> Restricted HTML -> export path is forbidden.

## 47. Narou export

Ruby is exported as `｜base《reading》`. Notes and metadata are excluded;
bold, italic, and emphasis decoration are dropped; heading text is retained;
the Narou exporter defines separator output; and block boundaries are
paragraphs.

Target-specific constraints do not enter the Canonical Schema. Formatting that
cannot be represented in the target format degrades while retaining the prose
and produces a warning.

The common response is:

```json
{
  "format": "narou",
  "media_type": "text/plain",
  "content": "...",
  "suggested_filename": "...",
  "warnings": []
}
```

The export endpoint is separate from Draft GET.

## 48. MCP contract

The MCP tool count remains **59**. No new draft tools are added. The existing
`episode_draft_get`, `episode_draft_save`, `episode_draft_history`, and
`episode_context` tools are extended.

## 49. TipTap boundary

TipTap JSON is not a CORE, API, MCP, or SQLite contract. The boundary is:

```text
Canonical Document
        <-> CORE Restricted HTML
        <-> WEBUI adapter
        <-> TipTap
```

Before full Edit implementation, a semantic round-trip feasibility test is
required. If feasibility fails, implementation returns to design review; the
contract is not changed opportunistically.

## 50. API v1 exception

The Phase E draft cutover removes the `body` contract and is a breaking change
for draft endpoints. The whole API is not versioned to v2. This is an explicit
pre-1.0 first-party structured-draft cutover exception, and legacy `body`
compatibility is not provided.

The post-certification v1 draft contract becomes the new baseline.

## 51. Runtime isolation

Migration inventory is read by the current CORE runtime. Merely placing an
unapplied 005 in the same checkout as the stable runtime may affect the old
project 2126: a write connection may auto-apply it, while a read-only
connection may reject the database for migration mismatch.

From E2 onward, the stable Phase D runtime checkout must therefore be isolated
from the Phase E checkout containing migration 005. E0 and E1 do not create
005; the destructive-migration isolation is required before E2 begins.

## 52. Development phases

### E0 — Formal Specification

Record this approved design. Do not implement E1 as part of E0.

### E1 — Document Engine

Implement the Document Engine without migration 005. After review, E1 may be
merged to main.

Before E2, confirm the stable runtime checkout. If necessary, create a
dedicated checkout/worktree for destructive-migration isolation.

### E2 — Backend Cutover

Implement migration 005, Repository, DraftService, API, MCP, and context as
one atomic backend implementation unit.

### E3 — Backend Certification

Certify the backend against an isolated disposable database.

### E4 — WEBUI Read

Implement the Read-first WEBUI projection and raw metadata visibility.

### E5 — WEBUI Edit / TipTap

Implement the thin TipTap editor and explicit-save interaction.

E2 through E5 are committed, pushed, and reviewed at each stage, but none is
merged to main until Final Cutover. They share one Phase E integration line.

## 53. Final Cutover

Final Cutover occurs only after E1 through E5, tests, static checks, E2E,
ChatGPT review, and documentation reconciliation are complete.

The operational sequence is:

1. stop the stable runtime;
2. confirm that no database is open;
3. merge the Phase E integration line to main;
4. run main CI;
5. update the stable checkout;
6. inspect the contents of `data/2126`;
7. discard the old `data/2126` only after that inspection;
8. recreate `project_id=2126` through the official project-creation path;
9. apply migrations 001 through 005;
10. verify database integrity;
11. start the runtime; and
12. perform real certification.

Unexpected user files in `data/2126` must not be deleted automatically.

## 54. Out of scope

Phase E does not include:

- vertical writing;
- autosave;
- automatic ruby generation;
- a ruby dictionary;
- a generic arbitrary JSON editor;
- metadata-aware merge;
- automatic continuity enforcement;
- participant-based speaker restriction;
- an addressee attribute;
- links;
- images;
- tables;
- lists;
- arbitrary HTML;
- Kakuyomu exporter implementation;
- Markdown exporter implementation;
- Aozora exporter implementation;
- new MCP draft tools;
- TipTap JSON persistence;
- current stable-data migration;
- legacy `body` compatibility; or
- API v2 duplication.

## 55. Definition of Done

Phase E is complete only when all of the following hold:

- `document_json` is the only persistent manuscript representation;
- the legacy `body` dependency is removed;
- CORE owns Document Schema v1;
- structural validation applies on read and write;
- live references validate only changed references during normal save;
- historical revisions are not invalidated by current database changes;
- restore recovers the historical snapshot, metadata, and block IDs;
- Restricted HTML round-trips as specified;
- full snapshot deletion semantics work;
- arbitrary annotations are preserved;
- complex metadata is visible in the WEBUI;
- TipTap JSON is not persisted;
- CAS prevents silent overwrite;
- history is append-only;
- context is structured HTML;
- context truncation is whole-block;
- the MCP tool count is 59;
- the WEBUI is Read-first;
- saving is explicit;
- autosave is absent;
- Narou export is available through WEBUI/API;
- the exporter boundary is extensible;
- destructive migration runtime isolation is in place;
- old `data/2126` remains untouched until Final Cutover;
- a fresh 2126 database is created with migrations 001 through 005;
- real MCP/API/WEBUI E2E passes;
- CI, static checks, and tests pass;
- documentation matches the implementation;
- the post-certification draft API v1 is recorded as the baseline; and
- ChatGPT review is complete before Final Cutover.
