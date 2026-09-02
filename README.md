# NovelProduction

NovelProduction is the repository for the novel-production system. It is
organized as a monorepo so shared domain logic, the MCP adapter, the FastAPI
backend, the React/Vite WEBUI, the story database, and project documentation
can evolve together.

## Directory structure

```text
CORE/      shared domain, database, and application services
MCP/       MCP adapter and stdio runtime
API/       Phase B FastAPI HTTP API
WEBUI/     React/Vite Phase D web UI
data/      repository-wide story database location
docs/      design specifications and implementation plans
```

Phase A through Phase D are complete. Phase D final stable WEBUI dogfood passed;
the WEBUI covers the Phase 1–3 administration surface with explicit Save and
conflict handling, production static serving, browser E2E, and stable
certification. Phase E is COMPLETE and Final Cutover is PASS. The Final Cutover
certified product/runtime baseline was
`9120d7b80c5035498995e0a03fcb716976ee966e`. The stable v1.0 runtime used migrations
001–005, and stable project `2126` was freshly recreated through the official
project-creation path. The canonical structured manuscript architecture is now
the stable baseline, including `document_json` persistence, the WEBUI Read/Edit
flow, TipTap explicit-save editing, and Narou export. The v1.0 baseline remains
documented at 59 MCP tools; Fiction Style Analysis v1.1 SA-I adds a separate
six-tool `style_analysis` group for an effective total of 65, with the existing
59 preserved. The API remains `/api/v1`, and `API/` is the sole runtime data-access boundary
for the shared services. See the [Phase E Final Cutover report](docs/superpowers/reports/2026-08-31-phase-e-final-cutover.md)
for detailed evidence.

The old pre-cutover `2126` remains preserved at
`data\.phase-e-backup-2126-20260831-074618` pending a separate cleanup
decision.

Phase C converts `MCP/` into a stateless HTTP adapter. It preserves the
existing 55 project-data tool names, requires an explicit `project_id` on each
of them, and adds `project_list`, `project_get`, `project_create`, and
`project_update` for the v1.0 59-tool baseline. SA-I's separate six-tool group
is documented in `docs/features/fiction-style-analysis/detailed-design/16-external-agent-mcp.md`.
MCP uses one
shared HTTP client per process and fails closed with `BACKEND_UNAVAILABLE` when
the API cannot be reached; it has no CORE or SQLite fallback. No repository
story database or generated artifacts are committed.

The MCP API URL defaults to `http://127.0.0.1:8765` and can be overridden by
`NOVEL_API_URL` or the CLI `--api-url` option. FastAPI serves a production
frontend build when started with `--webui-dist`; API routes retain precedence
over the SPA fallback. The certified stable API/MCP/Tunnel/Connector runtime is
documented in the [Phase E Final Cutover report](docs/superpowers/reports/2026-08-31-phase-e-final-cutover.md).

The WEBUI development and production-style run commands, trusted-LAN warning,
and isolated Chromium E2E workflow are documented in
`docs/runbooks/phase-d-webui.md`.

## Phase B API runtime

Run the API from `API/` with a temporary or otherwise disposable sandbox data
root. For example, in PowerShell:

```powershell
$sandboxData = Join-Path ([System.IO.Path]::GetTempPath()) "novelproduction-api-sandbox"
uv run novel-api --data-root $sandboxData
```

The default bind is `0.0.0.0:8765`. Host, port, and data root are configurable;
if the configured port cannot be bound, startup fails instead of selecting a
different port. The initial API has no authentication and is intended only for
a trusted LAN. Do not expose it directly to the public Internet.

Development CORS is disabled by default. A Vite development origin may be
enabled explicitly, for example with
`NOVEL_DEV_CORS_ORIGIN=http://127.0.0.1:5173`. Only that exact origin is
allowed; wildcard CORS is rejected.

## Data ownership

`data/` belongs to NovelProduction as a whole rather than to the MCP component.
The planned SQLite database will be the canonical source of truth for story
data; export formats such as Markdown or HTML will remain derived outputs.
