# NovelProduction Phase E — Final Cutover Report

Date: 2026-08-31

## Status

- Phase E: COMPLETE
- Final Cutover: PASS
- Final Connector Dogfood: PASS

This report is the canonical tracked evidence for the Phase E Final Cutover.

## Final Cutover promotion

- Pre-cutover main: `618ad6b231c06302f910cef3a35fa416f52d6699`
- Cutover-certified product/runtime SHA: `9120d7b80c5035498995e0a03fcb716976ee966e`
- Main CI for cutover SHA: `33339860430`
- Attempt: `1`

| Job | Conclusion |
| --- | --- |
| core | PASS |
| api | PASS |
| mcp | PASS |
| invariants | PASS |
| webui | PASS |
| webui-e2e | PASS |

## Stable pre-cutover anchor

- Old stable code SHA: `24b97a5b4feb819a51e6bb65e8f57e6798e0f69e`
- Old project: `2126`
- Old working title: `2126`
- Old status: `active`
- Old `story.db` SHA-256: `local cutover evidence参照`

The available local cutover evidence records only an abbreviated old database
hash. The omitted value is not inferred here.

## Backup

- Preserved old project backup: `data\.phase-e-backup-2126-20260831-074618`
- Backup deleted: no
- Rollback used: no

## Fresh project recreation

- Fresh stable project: `2126`
- Creation: official `ProjectRegistry.create()`
- Status: `active`
- Metadata: `ok`

Migrations applied:

- `001_initial.sql`
- `002_search.sql`
- `003_narrative.sql`
- `004_drafts.sql`
- `005_structured_drafts.sql`

Database verification:

- `integrity_check = ok`
- `foreign_key_check = 0 rows`
- `drafts.document_json` present
- legacy `body` absent
- legacy `content_hash` absent
- append-only trigger: PASS
- revision uniqueness/index: PASS

## Runtime

Stable checkout during certified runtime was detached at
`9120d7b80c5035498995e0a03fcb716976ee966e`.

- API: `127.0.0.1:8765`
- Tunnel: `127.0.0.1:8080`
- Production WEBUI: FastAPI same-origin production build

Local certification:

- API: PASS
- WEBUI: PASS
- Browser non-GET: `0`
- Browser critical console errors: `0`
- MCP stdio: PASS
- MCP tool count: `59`
- `project_select`: absent
- Tunnel: PASS

Process IDs are intentionally not recorded as permanent architecture facts.

## Connector dogfood

Final ChatGPT Connector read-only dogfood: PASS.

`project_get(project_id="2126")`:

- `project_id = 2126`
- `status = active`
- `metadata_state = ok`
- `health = ok`

`work_get(project_id="2126")`:

- `id = 1`
- `slug = main`
- `working_title = 2126`

Fresh narrative state was empty:

- `chapter_list = []`
- `character_search = []`
- `world_fact_search = []`
- `timeline_event_search = []`
- `information_search = []`

The manuscript had no chapter, so there was no valid episode and no draft
target. A nonexistent episode was not forced.

All project-scoped calls explicitly used `project_id="2126"`, and responses
confirmed `project_id = 2126`.

The Connector contract remained unchanged: `project_select` was absent, and no
direct SQLite fallback was observed through externally visible Connector
behavior. This fallback statement is limited to Connector behavior; internal
runtime inspection was not part of the Connector dogfood.

Connector writes: none.

Runtime, Tunnel, and Connector configuration changes during Connector dogfood:
none.

## Safety

- No force push
- No history rewrite
- No synthetic stable chapter, episode, scene, character, or draft fixtures
- No Connector configuration change
- Old backup preserved
- Rollback unused
- Cutover write limited to intentional fresh project recreation
- Connector certification read-only

## Certification inheritance

- E3 supplied disposable backend/write semantic certification.
- E5 supplied browser/editor/write UX certification.
- Final stable certification intentionally avoided synthetic persistent story fixtures.
- Final Connector certification was read-only.
