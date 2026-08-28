# NovelProduction Phase D WEBUI Implementation Plan

> **For agentic workers:** Execute this plan sequentially as a single agent. Use `superpowers:executing-plans` task-by-task. Do not use subagents, multi-agent delegation, parallel agent work, model escalation, or separate-agent review. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a trusted-LAN React/Vite WEBUI that covers the current Phase 1–3 NovelProduction administration surface through the existing FastAPI boundary, with explicit save, optimistic-concurrency conflict UX, project switching, and production static serving.

**Architecture:** `WEBUI` is an independent HTTP client of `/api/v1`; it never imports CORE or accesses SQLite. Browser location owns project/section/entity selection, TanStack Query owns server state, React local state owns unsaved form state, and no browser selection changes MCP behavior. Phase D remains plain-text for manuscript drafts; structured document persistence and TipTap are Phase E only.

**Tech Stack:** React, TypeScript, Vite, React Router, TanStack Query, dnd-kit, app-owned shadcn/ui-style primitives, Vitest, React Testing Library, user-event, MSW, Playwright, npm, Node 22.

**Spec:** `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

**Tracking:** Issue #10, parent Epic #6.

**Reviewed baseline:** `75a887b4cf5290f6a6e7cba1afa1e2ea21dc4cc0` after Phase C completion and Issue #9 closure.

## Global Constraints

- Phase D is split into D1–D5 reviewable PRs. Do not implement all Phase D in one PR.
- Base every implementation PR on the latest reviewed `main`; wait for ChatGPT review before starting the next block.
- `WEBUI` uses HTTP only: `WEBUI -> API -> CORE -> SQLite`.
- Do not add a server-global or client-global mutable current-project singleton. The URL is the canonical browser project selection state.
- Do not change the MCP contract or tool inventory; MCP remains 59 tools and explicit-project.
- Do not add migration `005`, TipTap, structured draft persistence, NovelProduction Document Schema v1, or Phase E code.
- Do not implement Issue #5 narrative retirement/delete semantics.
- Do not add authentication, public-Internet deployment support, project deletion, general entity delete/retire, automatic prose generation, Phase 4 continuity analysis, or rich timeline/relationship graph visualization.
- During implementation, do not read from or write to the stable `data/2126/story.db`; automated tests and dogfood use temporary data roots/projects only.
- Do not modify or restart the stable Tunnel or ChatGPT Connector during implementation PRs.
- Existing migrations `001`–`004` remain unchanged and migration `005` remains absent.
- Forms use explicit Save. No silent auto-save, automatic conflict retry, last-write-wins overwrite, or semantic auto-merge.
- API JSON/Any persistence fields stay governed by existing API semantics; WEBUI must not invent clear/unset behavior that the API does not support.
- Production/common use stays trusted-LAN only and unauthenticated.

---

## 1. Locked Frontend Architecture

### 1.1 Repository target structure

```text
WEBUI/
└─ frontend/
   ├─ package.json
   ├─ package-lock.json
   ├─ vite.config.ts
   ├─ tsconfig.json
   ├─ tsconfig.app.json
   ├─ tsconfig.node.json
   ├─ eslint.config.js
   ├─ index.html
   └─ src/
      ├─ main.tsx
      ├─ app/
      │  ├─ router.tsx
      │  ├─ providers.tsx
      │  ├─ queryClient.ts
      │  └─ styles.css
      ├─ api/
      │  ├─ client.ts
      │  ├─ errors.ts
      │  ├─ jsonFields.ts
      │  ├─ queryKeys.ts
      │  └─ types.ts
      ├─ components/
      │  ├─ layout/
      │  └─ ui/
      ├─ features/
      │  ├─ projects/
      │  ├─ dashboard/
      │  ├─ structure/
      │  ├─ world/
      │  ├─ characters/
      │  ├─ timeline/
      │  ├─ information/
      │  ├─ manuscript/
      │  ├─ canon/
      │  └─ conflicts/
      └─ test/
         ├─ setup.ts
         ├─ server.ts
         └─ handlers.ts
```

Keep files responsibility-focused. Do not create a generic application store. App-owned `components/ui/*` primitives follow the shadcn/ui ownership model but use ordinary React + CSS variables in Phase D; do not introduce a component framework or Tailwind solely to satisfy the label “shadcn/ui-style”.

### 1.2 State ownership

```text
React Router URL state -> project_id, section, selected entity ID, detail route
TanStack Query         -> HTTP/server state and cache
React local state      -> unsaved form values, dirty state, conflict dialog state
```

All project-scoped query keys start with the project identity, e.g. `['project', projectId, 'work']`. A query key that can return project data without `projectId` is a test failure.

When routing from `/projects/A/...` to `/projects/B/...`, project-local editor components must remount or reset from the new route params. Cached A data may remain in TanStack Query under A-scoped keys, but must never render under B routes.

### 1.3 Router

Use routes conceptually equivalent to:

```text
/
/projects/:projectId/dashboard
/projects/:projectId/structure
/projects/:projectId/structure/chapters/:chapterId
/projects/:projectId/structure/episodes/:episodeId
/projects/:projectId/structure/scenes/:sceneId
/projects/:projectId/world
/projects/:projectId/world/:factId
/projects/:projectId/characters
/projects/:projectId/characters/:characterId
/projects/:projectId/timeline
/projects/:projectId/timeline/:eventId
/projects/:projectId/information
/projects/:projectId/information/:informationId
/projects/:projectId/manuscript
/projects/:projectId/manuscript/:episodeId
/projects/:projectId/canon
```

`/` is the project picker/management screen. A missing/invalid explicit project route shows a project-level error and offers return to `/`; it must not silently switch to another project.

### 1.4 Navigation/layout

Persistent desktop sidebar sections:

```text
Dashboard
Structure
World
Characters
Timeline
Information
Manuscript
Canon / History
```

Desktop: `sidebar | list/tree | detail/editor`.

Narrow/mobile: sidebar becomes a drawer/collapsible navigation; selecting a list/tree item navigates to a full-width detail/editor route. Do not preserve a compressed three-column layout on narrow screens.

---

## 2. HTTP Client and Error Contract

### 2.1 Base URL

Feature code always calls relative `/api/v1` URLs. Development Vite proxies `/api` to `http://127.0.0.1:8765`. Production is same-origin.

Do not branch feature code on development vs production URLs. Keep existing `NOVEL_DEV_CORS_ORIGIN` support intact for other development uses, but the Phase D frontend itself defaults to the Vite proxy.

### 2.2 API success shapes

Project management endpoints return their declared project models directly. Project-scoped domain endpoints return:

```ts
export interface ProjectEnvelope<T> {
  project_id: string;
  data: T;
}
```

Direct API responses do **not** contain the MCP-only `ok` field.

### 2.3 Error shape

```ts
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    project_id: string | null;
    details: Record<string, unknown>;
  };
}
```

Implement a single `ApiError` class carrying HTTP status, code, message, project ID, and details. `apiRequest<T>()` must:

1. send/parse JSON;
2. reject non-2xx responses as `ApiError` when the common envelope is valid;
3. use a safe fallback error for malformed bodies;
4. for project-scoped success, verify response `project_id` exactly equals the requested route project before returning `data`.

### 2.4 Conflict behavior

For HTTP 409 / `VERSION_CONFLICT`:

- preserve local unsaved state;
- use `details.current_resource` when present;
- if `current_resource` is absent, issue the relevant read-only refetch and use that as the latest resource;
- show Local unsaved edits vs Latest database resource;
- user may discard local edits and load latest, or keep local edits and close the comparison;
- never automatically resubmit with the latest version.

The conflict component is generic, but the mapping from a resource to its display fields remains feature-owned.

---

## 3. JSON-backed Fields

Current CORE records serialize JSON columns as **strings**, while request schemas accept JSON values that API handlers compact-encode before persistence. Therefore WEBUI response types keep these fields as `string`; editor forms convert them to pretty JSON text and parse them back to JSON values on Save.

Fields include:

```text
Work.themes_json
WorldFact.details_json
Character.profile_json
CharacterState.beliefs_json
CharacterState.state_json
InformationItem.notes_json
Episode.foreshadowing_notes_json
```

`jsonFields.ts` provides:

```ts
formatStoredJson(value: string): string
parseJsonEditor(text: string): unknown
```

Invalid JSON is a client validation error and is never sent. Do not reinterpret empty text as a database clear operation unless the target API has explicit clear semantics.

---

## 4. Implemented Response/Domain Type Inventory

Types below mirror the reviewed CORE dataclasses and API serialization. Do not add convenience properties such as `CharacterRecord.name`; dataclass properties are not serialized by `serialize_value()`.

```ts
export interface ProjectSummary {
  project_id: string;
  status: 'active' | 'archived';
  metadata_state: 'ok' | 'missing' | 'invalid';
  working_title: string | null;
  created_at: string | null;
  updated_at: string | null;
  health: 'ok' | 'degraded';
}

export interface WorkRecord {
  id: number; slug: string; working_title: string; genre: string;
  premise: string; themes_json: string; description: string;
  production_status: string; created_at: string; updated_at: string; version: number;
}

export interface WorldFactRecord {
  id: number; work_id: number; topic_key: string; category: string; title: string;
  statement: string; details_json: string; valid_from: string | null;
  valid_to: string | null; canon_status: string; importance: number; version: number;
  created_at: string; updated_at: string;
}

export interface TimelineParticipantRecord { event_id: number; character_id: number; role: string; }
export interface TimelineEventRecord {
  id: number; work_id: number; event_key: string; time_start: string | null;
  time_end: string | null; date_precision: string; date_display: string; title: string;
  description: string; category: string; location_world_fact_id: number | null;
  cause_summary: string; consequence_summary: string; canon_status: string;
  importance: number; version: number; created_at: string; updated_at: string;
  participants: TimelineParticipantRecord[];
}
export interface TimelineRelationRecord {
  id: number; work_id: number; source_event_id: number; target_event_id: number;
  relation_type: string; version: number;
}

export interface CharacterRecord {
  id: number; work_id: number; character_key: string; display_name: string;
  entity_type: string; description: string; birth_date: string | null;
  death_date: string | null; physical_description: string; occupation: string;
  core_beliefs: string; goals: string; fears: string; personality: string;
  speech_style: string; ai_attitude: string; genetic_modification_attitude: string;
  private_notes: string; profile_json: string; canon_status: string; version: number;
  created_at: string; updated_at: string;
}

export interface RelationshipRecord {
  id: number; work_id: number; source_character_id: number; target_character_id: number;
  relationship_type: string; description: string; canon_status: string;
  valid_from_episode_id: number | null; valid_to_episode_id: number | null;
  version: number; created_at: string; updated_at: string;
}

export interface CanonChange {
  entity_type: string; entity_id: number; action: string;
  before_payload: Record<string, unknown>; after_payload: Record<string, unknown>;
}
export interface CanonDecisionRecord { id: number; summary: string; reason: string; changes: CanonChange[]; }

export interface ChapterRecord {
  id: number; work_id: number; position: number; title: string; summary: string;
  purpose: string; canon_status: string; production_status: string; version: number;
  created_at: string; updated_at: string;
}
export interface EpisodeRecord {
  id: number; work_id: number; chapter_id: number; position: number; title: string;
  summary: string; purpose: string; foreshadowing_notes_json: string;
  canon_status: string; production_status: string; version: number;
  created_at: string; updated_at: string;
}
export interface SceneRecord {
  id: number; work_id: number; episode_id: number; position: number; title: string;
  summary: string; purpose: string; canon_status: string; production_status: string;
  version: number; created_at: string; updated_at: string;
}

export interface EpisodeReferenceRecord {
  id: number; work_id: number; episode_id: number; reference_type: string;
  target_id: number; role: string | null; created_at: string;
}
export interface CharacterStateRecord {
  id: number; work_id: number; character_id: number; episode_id: number;
  physical_state: string; emotional_state: string; beliefs_json: string;
  location_world_fact_id: number | null; state_json: string; version: number;
  created_at: string; updated_at: string;
}
export interface InformationItemRecord {
  id: number; work_id: number; statement: string; truth_status: string;
  authoring_guard: string; notes_json: string; canon_status: string;
  importance: number; version: number; created_at: string; updated_at: string;
}
export interface ReaderDisclosureRecord {
  id: number; work_id: number; information_item_id: number; episode_id: number;
  version: number; created_at: string; updated_at: string;
}
export interface CharacterKnowledgeEventRecord {
  id: number; work_id: number; character_id: number; information_item_id: number;
  episode_id: number; knowledge_state: string; note: string; version: number;
  created_at: string; updated_at: string;
}
export interface EffectiveKnowledgeRecord {
  knowledge_state: string; event_episode_id: number; event_id: number; event_version: number;
  information_item: InformationItemRecord;
}

export interface DraftRecord {
  id: number; work_id: number; episode_id: number; revision: number;
  parent_draft_id: number | null; body: string; source_agent: string | null;
  change_summary: string; content_hash: string; created_at: string;
}
export interface DraftMetadata {
  id: number; episode_id: number; revision: number; parent_draft_id: number | null;
  source_agent: string | null; change_summary: string; content_hash: string;
  body_chars: number; created_at: string;
}
```

Outline/context types mirror `CORE/src/novel_core/models/outline.py` and `context.py` exactly: `SafeCharacterProfile`, `OutlineParticipant`, `SafeWorldFact`, `SafeTimelineEvent`, `SafeInformationItem`, `RevealBoundary`, `ProtectedInformationGuard`, `OutlineReferences`, `EpisodeOutline`, `EffectiveCharacterState`, `EffectiveRelationship`, `ParticipantKnownInformation`, `ContextParticipant`, `ReaderContext`, `PreviousEpisodeSummary`, `RecentContext`, and `EpisodeContext`.

Existing aggregated API types:

```ts
export interface OutlineEpisodeView { episode: EpisodeRecord; scenes: SceneRecord[]; }
export interface OutlineChapterView { chapter: ChapterRecord; episodes: OutlineEpisodeView[]; }
export interface OutlineView { chapters: OutlineChapterView[]; }
export interface DashboardView { work: WorkRecord; chapter_count: number; episode_count: number; scene_count: number; }
export interface EpisodeView {
  episode: EpisodeRecord;
  scenes: SceneRecord[];
  episode_references: EpisodeReferenceRecord[];
  outline: EpisodeOutline;
  context: EpisodeContext;
  latest_draft: DraftRecord | null;
  recent_draft_history: DraftMetadata[];
}
```

---

## 5. Current HTTP Inventory Used by WEBUI

All domain paths are prefixed by `/api/v1/projects/{project_id}` unless shown otherwise.

### Project/work/views

| Method | Path | Request | Response / CAS |
| --- | --- | --- | --- |
| GET | `/api/v1/projects?include_archived=` | query | `ProjectListResponse` |
| POST | `/api/v1/projects` | `ProjectCreateRequest` | `ProjectSummary`, 201 |
| GET | `/api/v1/projects/{project_id}` | — | `ProjectSummary` |
| PATCH | `/api/v1/projects/{project_id}` | `ProjectStatusRequest` | `ProjectSummary` |
| GET | `/work` | — | `ProjectEnvelope<WorkRecord>` |
| PATCH | `/work` | `WorkUpdate` | `expected_version`, enriched conflict |
| GET | `/views/dashboard` | — | `DashboardView` |
| GET | `/views/outline` | — | `OutlineView` |
| GET | `/views/episodes/{episode_id}` | — | `EpisodeView` |

### World/timeline/characters/canon

| Method | Path | Request | Response / CAS |
| --- | --- | --- | --- |
| POST | `/world-facts` | `WorldFactCreate` | `WorldFactRecord` |
| GET | `/world-facts/search?query=&limit=` | query | `WorldFactRecord[]`; blank query returns empty |
| GET | `/world-facts/{fact_id}` | — | `WorldFactRecord` |
| PATCH | `/world-facts/{fact_id}` | `WorldFactUpdate` | `expected_version`, enriched conflict |
| POST | `/timeline/events` | `TimelineEventCreate` | `TimelineEventRecord` |
| GET | `/timeline/events/search?query=&limit=` | query | `TimelineEventRecord[]`; blank query returns empty |
| GET | `/timeline/events/{event_id}` | — | `TimelineEventRecord` |
| PATCH | `/timeline/events/{event_id}` | `TimelineEventUpdate` | `expected_version`, enriched conflict |
| GET | `/timeline/range?start=&end=&limit=` | query | `TimelineEventRecord[]` |
| POST | `/timeline/events/{event_id}/move` | `TimelineMove` | `expected_version`, enriched conflict |
| POST | `/timeline/relations` | `TimelineRelationCreate` | `TimelineRelationRecord`; create-only in current API |
| POST | `/characters` | `CharacterCreate` | `CharacterRecord` |
| GET | `/characters/search?query=&limit=` | query | `CharacterRecord[]`; blank query returns empty |
| GET | `/characters/{character_id}` | — | `CharacterRecord` |
| PATCH | `/characters/{character_id}` | `CharacterUpdate` | `expected_version`, enriched conflict |
| GET | `/relationships?character_id=&limit=` | query | `RelationshipRecord[]`; omitting character ID lists relationships |
| POST | `/relationships` | `RelationshipCreate` | `RelationshipRecord` |
| PATCH | `/relationships/{relationship_id}` | `RelationshipUpdate` | `expected_version`, enriched conflict |
| POST | `/canon/status` | `CanonStatusSet` | `CanonDecisionRecord`, CAS by entity version |
| GET | `/canon/decisions/search?query=&limit=` | query | `CanonDecisionRecord[]`; blank query returns empty |
| GET | `/canon/decisions/{decision_id}` | — | `CanonDecisionRecord` |

### Narrative/information/authoring

| Method | Path | Request | Response / CAS |
| --- | --- | --- | --- |
| GET/POST | `/chapters` | `ChapterCreate` on POST | `ChapterRecord[]` / `ChapterRecord` |
| PATCH | `/chapters/{chapter_id}` | `ChapterUpdate` | `expected_version`, enriched conflict |
| POST | `/chapters/{chapter_id}/reorder` | `Reorder` | `expected_version`, enriched conflict |
| GET/POST | `/chapters/{chapter_id}/episodes` | `EpisodeCreate` on POST | `EpisodeRecord[]` / `EpisodeRecord` |
| GET/PATCH | `/episodes/{episode_id}` | `EpisodeUpdate` on PATCH | `EpisodeRecord`; enriched conflict |
| POST | `/episodes/{episode_id}/reorder` | `Reorder` | enriched conflict |
| GET/POST | `/episodes/{episode_id}/scenes` | `SceneCreate` on POST | `SceneRecord[]` / `SceneRecord` |
| GET/PATCH | `/scenes/{scene_id}` | `SceneUpdate` on PATCH | `SceneRecord`; enriched conflict |
| POST | `/scenes/{scene_id}/reorder` | `Reorder` | enriched conflict |
| GET/POST | `/episodes/{episode_id}/references` | `EpisodeReferenceAdd` on POST | `EpisodeReferenceRecord[]` / record |
| DELETE | `/episodes/{episode_id}/references/{reference_type}/{target_id}` | — | removed result |
| GET | `/characters/{character_id}/states/{episode_id}` | — | effective `CharacterStateRecord | null` |
| PUT | `/characters/{character_id}/states/{episode_id}` | `CharacterStateSet` | create/update; `expected_version` optional/new-vs-existing semantics |
| GET | `/characters/{character_id}/states` | — | `CharacterStateRecord[]` history |
| POST | `/information` | `InformationCreate` | `InformationItemRecord` |
| GET | `/information/search?query=&limit=` | query | `InformationItemRecord[]`; blank query returns empty |
| GET/PATCH | `/information/{information_item_id}` | `InformationUpdate` on PATCH | `InformationItemRecord`; enriched conflict |
| PUT | `/information/{information_item_id}/reader-disclosure` | `ReaderDisclosureSet` | `ReaderDisclosureRecord`; optional/new-vs-existing version semantics |
| PUT | `/characters/{character_id}/knowledge/{information_item_id}` | `CharacterKnowledgeSet` | `CharacterKnowledgeEventRecord`; optional/new-vs-existing version semantics |
| GET | `/characters/{character_id}/knowledge?episode_id=` | query | `EffectiveKnowledgeRecord[]` |
| GET | `/episodes/{episode_id}/outline` | — | `EpisodeOutline` |
| GET | `/episodes/{episode_id}/context` | — | `EpisodeContext` |
| GET | `/episodes/{episode_id}/draft?revision=` | query | `DraftRecord | null` |
| GET | `/episodes/{episode_id}/drafts?limit=` | query | `DraftMetadata[]` |
| POST | `/episodes/{episode_id}/drafts` | `DraftSave` | append-only `DraftRecord`; parent CAS conflict includes latest draft |

Request schemas remain the implemented Pydantic models in `API/src/novel_api/schemas/`; frontend payloads must match them exactly and omit untouched optional PATCH fields.

---

## 6. Required API Gaps Discovered During Planning

Phase B intentionally optimized around MCP search commands. Several browse screens cannot enumerate their current resources because blank search queries return empty, and some current write-only relations lack a read endpoint. Phase D therefore needs the following **read-only, no-new-domain-semantics** additions.

1. `GET /api/v1/projects/{project_id}/world-facts?limit=&offset=` -> `WorldFactRecord[]` ordered by ID.
2. `GET /api/v1/projects/{project_id}/characters?limit=&offset=` -> `CharacterRecord[]` ordered by ID.
3. `GET /api/v1/projects/{project_id}/timeline/events?limit=&offset=` -> `TimelineEventRecord[]` in chronology order then ID.
4. `GET /api/v1/projects/{project_id}/timeline/relations?event_id=&limit=&offset=` -> `TimelineRelationRecord[]`; optional event filter matches either source or target.
5. `GET /api/v1/projects/{project_id}/information?limit=&offset=` -> `InformationItemRecord[]` ordered by ID.
6. `GET /api/v1/projects/{project_id}/information/{information_item_id}/reader-disclosure` -> `ReaderDisclosureRecord | null` using the already-implemented `DisclosureService.get_reader_disclosure()`.
7. `GET /api/v1/projects/{project_id}/canon/decisions?limit=&offset=` -> `CanonDecisionRecord[]` ordered by ID.

List endpoints use `limit` 1–100 and `offset >= 0`. The frontend loads the first page and offers Load more while a page returns `limit` items. Do not add total-count queries or a generic pagination framework in Phase D.

Implement list operations in existing CORE repositories/services rather than raw SQL in API handlers. They are read-only and must use `open_project_read_services()`.

No other API additions are required for the approved Phase D screens. In particular, do not add delete APIs, timeline relation update/delete, project deletion, or structured-draft APIs.

---

## 7. Feature Behavior

### 7.1 Projects

- Picker uses active list by default; an Include archived toggle requests `include_archived=true`.
- Create form: `working_title` required, `project_id` optional. On success navigate to `/projects/<id>/dashboard`.
- Archive/unarchive uses status only. If the currently selected project is archived successfully, navigate to `/`.
- Display `metadata_state` and `health`; degraded/missing metadata must not hide a discoverable project.
- No project delete control.

### 7.2 Dashboard and Work

Dashboard uses `/views/dashboard` for title/status/count summary. Work editor loads `/work` and saves only changed fields plus required `working_title` and `expected_version` required by the implemented `WorkUpdate` schema. `themes_json` uses the JSON editor conversion described above.

### 7.3 Structure

Use `/views/outline` for tree composition. Tree is Chapter -> Episode -> Scene.

Supported actions only:

- create Chapter/Episode/Scene;
- edit current fields;
- reorder using dnd-kit and existing reorder endpoints;
- add/remove episode references.

No delete/retire operation is shown. Reorder default is mutation -> refetch; do not keep an optimistic order unless rollback is deterministic and covered by tests.

Episode detail uses `/views/episodes/{episode_id}` and presents tabs/sections for Episode, Scenes, References, Outline, Context, and Draft history. D2 does not implement the manuscript editor itself; it may link to the Manuscript route.

### 7.4 World

Initial browse uses new GET `/world-facts`; non-empty search uses existing `/world-facts/search`. Detail uses GET by ID. Create/update fields follow `WorldFactCreate`/`WorldFactUpdate`. `details_json` uses JSON conversion. `canon_status` is displayed; status changes use the existing canon-status command where the resource update schema does not expose it.

### 7.5 Characters

Initial browse uses new GET `/characters`; non-empty search uses existing character search. Character detail tabs:

```text
Profile | Relationships | States | Knowledge
```

Profile fields mirror `CharacterCreate`/`CharacterUpdate`. Relationships use the existing relationship list/create/update API; relationship valid-from/to clear actions use the implemented `clear_valid_from` / `clear_valid_to` flags and no invented null semantics.

States use outline episodes as the episode selector, effective-state GET, history GET, and existing PUT. Knowledge uses a selected episode and current effective knowledge GET; do not build an N×M knowledge matrix or fan out across every character automatically.

### 7.6 Timeline

Initial browse uses new list-events endpoint; search and date-range use the existing endpoints. Detail supports event create/update/move and participant editing. Relations are listed with the new read endpoint and can only be created, matching current domain capabilities. No relation update/delete UI and no graph framework in Phase D.

### 7.7 Information

Initial browse uses new GET `/information`; non-empty search uses existing search. Item fields mirror `InformationCreate`/`InformationUpdate`.

Reader Disclosure tab reads the new getter, then uses existing PUT. Character Knowledge tab uses a character picker plus episode picker and the existing effective knowledge read/set operations. Do not invent a bulk matrix API.

### 7.8 Canon / History

Initial history uses new decision list; non-empty search uses current search; details use current decision GET. Canon status action uses existing `/canon/status`. UI may surface status actions on domain forms as well, but CORE/API remains the source of truth for reason/policy requirements.

### 7.9 Manuscript — Phase D plain-text only

Episode selection comes from outline data. Editor shows latest plain draft and recent history. Saving always POSTs a new revision:

```json
{
  "body": "...",
  "expected_parent_draft_id": 123,
  "source_agent": "webui",
  "change_summary": "..."
}
```

If no draft exists, `expected_parent_draft_id` is `null`. A draft conflict preserves local body and compares against the returned latest draft. Never overwrite or modify an existing revision. No TipTap or structured JSON document appears in Phase D.

---

## 8. Explicit Save and Dirty Navigation

Every edit feature follows:

```text
read baseline + version
-> initialize local form
-> edit locally
-> explicit Save
-> build minimal legal payload
-> mutation
-> invalidate/refetch project-scoped queries
-> replace local baseline only after successful response
```

Untouched optional PATCH fields are omitted. Fields without API clear semantics cannot be cleared by inventing `null`/empty conventions. Relationship validity clear flags are the explicit exception because the API supports them.

Dirty forms use both router navigation blocking and `beforeunload`. The user can Stay or Discard and leave. Successful Save clears dirty state. Project switching is also navigation and must pass through the same guard.

---

## 9. Production Static Serving

D1 extends API settings with:

```python
ApiSettings(..., webui_dist: Path | None = None)
```

CLI/env precedence:

```text
--webui-dist > NOVEL_WEBUI_DIST > None
```

Rules:

- `webui_dist=None`: API-only mode behaves exactly as today.
- Explicit dist must exist, be a directory, and contain `index.html`; otherwise startup/app creation fails clearly.
- Register API routers first.
- Register a final GET/HEAD SPA/static fallback only when dist is configured.
- Existing files under dist are served with `FileResponse`; non-file frontend routes return `index.html`.
- Normalize/resolve candidate paths and never serve a path outside dist.
- Any path beginning `/api/v1` remains an API request and must never receive `index.html`; unknown API paths continue through the structured API 404 behavior.
- Static startup performs no database mutation.

Common production command:

```powershell
uv run novel-api `
  --data-root <data> `
  --host 0.0.0.0 `
  --port 8765 `
  --webui-dist <repo>\WEBUI\frontend\dist
```

Trusted LAN only; docs must explicitly warn against direct public-Internet exposure.

---

## 10. D1–D5 Delivery Blocks

### D1 — Frontend foundation, project shell, Dashboard/Work, production hosting

**Files:**
- Create `WEBUI/frontend/*` scaffold and `src/app`, `src/api`, `src/components`, `src/features/projects`, `src/features/dashboard`, `src/features/conflicts`.
- Modify `API/src/novel_api/config.py`, `API/src/novel_api/cli.py`, `API/src/novel_api/app.py`.
- Add API tests for static/SPA serving.
- Modify `.github/workflows/mcp-ci.yml` to add `webui` job only; preserve existing job names/behavior.

**Interfaces produced:** `apiRequest`, `ApiError`, project-scoped query key factory, shared shell/sidebar, project picker/create/archive, dashboard/work editor, generic conflict dialog, JSON field helpers, dirty-navigation guard, optional API `webui_dist` support.

- [ ] Write API tests first for API-only behavior, valid dist root, SPA deep route, asset serving, `/api/v1/health` precedence, unknown `/api/v1/*` not returning SPA, missing explicit dist failure, and path traversal refusal.
- [ ] Run focused API tests and confirm RED before static-serving implementation.
- [ ] Implement `webui_dist` settings/CLI/env resolution and safe SPA fallback; run focused tests GREEN.
- [ ] Scaffold Vite React TypeScript with npm; add React Router, TanStack Query, Vitest/RTL/user-event/MSW and lint/typecheck scripts. Do not add Redux/Zustand/Next/GraphQL.
- [ ] Write frontend tests for `apiRequest`, error parsing, project-ID envelope mismatch, JSON conversion, and project-scoped query keys; confirm RED, then implement helpers.
- [ ] Write routing/layout tests: picker at `/`, project dashboard route, sidebar links preserve `projectId`, and switching project routes cannot display old-project entity state.
- [ ] Implement app providers/router/layout and app-owned UI primitives.
- [ ] Write project-flow tests for include-archived, create->navigate, archive selected->picker, then implement.
- [ ] Write Work explicit-save tests including dirty state, minimal payload, expected version, successful invalidation, conflict comparison, and invalid JSON prevention; then implement Dashboard/Work.
- [ ] Add `webui` CI job: `npm ci`, `npm run lint`, `npm run typecheck`, `npm test -- --run`, `npm run build`.
- [ ] Run full CORE/API/MCP/invariants plus WEBUI checks before PR.

**D1 verification:**

```powershell
Set-Location WEBUI/frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
Set-Location ../../API
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
Set-Location ../MCP
uv run pytest -W error
uv run python scripts/check_repository_boundaries.py
Set-Location ..
git diff --check
```

### D2 — Structure/narrative administration

**Files:** add `features/structure/*`, dnd-kit dependencies, structure tests. No CORE/API additions expected.

- [ ] Add exact narrative/outline TypeScript types and API functions with project-scoped keys.
- [ ] Test and implement Chapter/Episode/Scene tree rendering from `/views/outline`.
- [ ] Test and implement create/update forms with explicit Save and conflict UX.
- [ ] Test and implement dnd-kit reorder; mutation sends `target_position` + entity `expected_version`, then refetches outline.
- [ ] Test and implement episode detail from `/views/episodes/{id}` including references, outline/context displays, and add/remove reference commands.
- [ ] Test narrow-route behavior: list/tree route -> selected detail full width.
- [ ] Run D1 checks plus focused structure tests.

### D3 — World, Characters, Timeline + browse API gaps

**Backend files:** existing world/character/timeline repositories/services/routes plus tests. Add only the list/read operations specified in Section 6.

- [ ] Write failing CORE tests for `WorldFactRepository/Service` list paging, `CharacterRepository/Service` list paging, timeline event list paging, and timeline relation list/filter paging.
- [ ] Implement minimal read-only repository/service methods; no new write semantics.
- [ ] Write failing API tests for the four new browse endpoints and project isolation/read-only connection behavior; implement routes using `open_project_read_services()`.
- [ ] Write and implement World browse/search/detail/create/update UI.
- [ ] Write and implement Character browse/search/profile/relationship/state/knowledge UI.
- [ ] Write and implement Timeline list/search/range/detail/move/participant/relation-create UI; relations remain read/create only.
- [ ] Verify query keys contain `projectId` and project switching with overlapping numeric IDs does not leak cached entities.
- [ ] Run CORE/API/MCP/WEBUI regression before PR.

### D4 — Information, Canon, plain Manuscript + remaining read API gaps

**Backend files:** information/disclosure/canon repository/service/routes plus tests. Add only Section 6 information/disclosure/canon reads.

- [ ] Write failing CORE/API tests for Information list paging, CanonDecision list paging, and reader-disclosure GET; implement minimal read-only methods/routes.
- [ ] Test and implement Information browse/search/editor with JSON notes validation.
- [ ] Test and implement Reader Disclosure current-state load/set and 409 refetch fallback when conflict details lack `current_resource`.
- [ ] Test and implement Character Knowledge editing using selected character + episode, not a bulk matrix.
- [ ] Test and implement Canon decision list/search/detail and canon-status action surfaces.
- [ ] Test and implement plain manuscript latest/history/new-revision flow with `source_agent='webui'`, parent CAS, local-body preservation on conflict, and no revision overwrite.
- [ ] Assert no TipTap, structured draft fields, or migration 005 exists.
- [ ] Run full regression before PR.

### D5 — Integration, responsive/accessibility polish, Playwright E2E, docs

**Files:** Playwright config/tests, integration fixes, responsive/accessibility fixes, trusted-LAN/run docs. No new product features.

- [ ] Add Playwright Chromium setup and a temporary-data-root API/WebUI test harness.
- [ ] E2E: create project through WEBUI, select it, edit Work via explicit Save.
- [ ] E2E: create Chapter -> Episode -> Scene and navigate tree/detail.
- [ ] E2E: create/read representative World or Character entity.
- [ ] E2E: induce `VERSION_CONFLICT` with an out-of-band API write and verify local-vs-latest comparison with no auto retry.
- [ ] E2E: append a plain-text draft revision and verify history.
- [ ] E2E: create two temporary projects with overlapping numeric IDs and prove UI project switching has no leakage.
- [ ] E2E: build frontend, start FastAPI with `--webui-dist`, verify `/`, a deep SPA route, static asset, and `/api/v1/health` from the same process.
- [ ] Check mobile/narrow routes, keyboard focus for dialogs/navigation, labels, loading/empty/error states, and visible Save/dirty state.
- [ ] Document development (`Vite :5173` + API `:8765`) and production/common same-origin command plus trusted-LAN warning.
- [ ] Add separate CI E2E job if runtime is material; Chromium only is sufficient for Phase D CI.
- [ ] Run all Python, frontend, build, and E2E checks before PR.

**D5 verification:**

```powershell
Set-Location WEBUI/frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
npx playwright test --project=chromium
Set-Location ../../CORE
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
Set-Location ../API
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
Set-Location ../MCP
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pre-commit run --all-files
uv run python scripts/check_repository_boundaries.py
Set-Location ..
python MCP/scripts/check_source_size.py
git diff --check
```

---

## 11. Testing Invariants Across All Blocks

Frontend tests must prove at least:

- API success/error parsing and safe malformed-response handling;
- project-scoped response identity validation;
- every project-data query key contains `projectId`;
- project switch cannot display old-project entity data;
- project create/archive/unarchive routing;
- list/detail navigation and responsive detail route behavior;
- explicit Save and dirty-navigation warning;
- version-conflict comparison and no auto retry;
- JSON editor validation/round-trip;
- structure tree/reorder/refetch;
- draft append-only save and parent conflict handling.

Backend gap tests must prove all new list/get routes are read-only, project-isolated, bounded by paging inputs, and use existing CORE services rather than API SQL.

No implementation test may access stable project `2126`.

---

## 12. CI End State

Keep the existing workflow name and `core`, `api`, `mcp`, `invariants` jobs. Add:

```text
webui:
  npm ci
  npm run lint
  npm run typecheck
  npm test -- --run
  npm run build

webui-e2e:   # D5
  build frontend
  install Chromium
  start temporary-data-root API/WebUI
  run Playwright
```

The existing MCP tool inventory assertion remains exactly 59. The invariants job continues to require only migrations 001–004.

---

## 13. Stable-data Safety and Dogfood

Implementation PRs D1–D5 use only temporary data roots. They do not start against, inspect, hash, copy, migrate, or write `data/2126/story.db`.

After all D1–D5 PRs are reviewed, merged, and main CI is green, perform a separate Phase D post-merge dogfood using stable `2126` only after explicit approval. Dogfood should first exercise read/navigation, then one separately approved reversible UI write with the same conflict/restore discipline used for Phase C. Tunnel/Connector behavior is not changed by Phase D.

---

## 14. Phase D Exit Criteria

Phase D is complete only when all are true:

1. D1–D5 reviewed and merged.
2. Main CI is green for CORE/API/MCP/invariants/WEBUI/E2E.
3. Browser can discover/switch/create/archive projects without server-global selection state.
4. Work and all current Phase 1–3 administrative domains are browseable and editable through implemented API semantics.
5. Chapter/Episode/Scene tree supports create/update/reorder without delete/retire invention.
6. Explicit Save and VERSION_CONFLICT comparison are proven.
7. Plain draft revisions remain append-only and save through parent CAS.
8. Production frontend build is served by FastAPI while `/api/v1/*` retains API precedence.
9. Two-project E2E proves no cross-project UI leakage.
10. Post-merge stable dogfood passes.
11. Migration 005 / TipTap / structured drafts remain absent.
12. Issue #10 may then be closed; Phase E begins only afterward.

## 15. Non-scope Checklist

Do not implement in Phase D:

- Phase E structured-draft editor;
- TipTap/ProseMirror;
- NovelProduction Document Schema v1;
- migration 005;
- Issue #5 retirement/delete behavior;
- project deletion;
- general entity physical delete/retire;
- authentication or public-Internet exposure;
- automatic prose generation;
- Phase 4 continuity analysis;
- rich timeline or relationship graph visualization;
- MCP contract/tool-count changes.

## 16. Self-review Result

- Spec coverage: Phase D routing, project management, complete Phase 1–3 administration surface, explicit save, conflict UX, responsive behavior, production static serving, testing, CI, and trusted-LAN boundary are mapped to D1–D5.
- API inventory: current implemented routes and CORE serialized records were used rather than assumed OpenAPI `Any` shapes.
- Required API gaps: seven narrow read-only endpoints identified; no write/domain-semantic additions required.
- Placeholder scan: no implementation task depends on TBD/TODO behavior.
- Phase boundary: TipTap/document schema/migration 005 remain exclusively Phase E.
