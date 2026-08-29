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

Phase A through Phase C are complete. The Phase D D1-D5 WEBUI implementation
is present pending final post-merge stable dogfood certification. `CORE/` owns
the SQLite lifecycle,
immutable migrations 001–004, configuration, errors, models, repositories,
initialization, and domain services. `API/` is the sole runtime data-access
boundary for the shared services under `/api/v1`.

Phase C converts `MCP/` into a stateless HTTP adapter. It preserves the
existing 55 project-data tool names, requires an explicit `project_id` on each
of them, and adds `project_list`, `project_get`, `project_create`, and
`project_update` for 59 tools total. MCP uses one shared HTTP client per
process and fails closed with `BACKEND_UNAVAILABLE` when the API cannot be
reached; it has no CORE or SQLite fallback. No repository story database or
generated artifacts are committed.

The MCP API URL defaults to `http://127.0.0.1:8765` and can be overridden by
`NOVEL_API_URL` or the CLI `--api-url` option. FastAPI serves a production
frontend build when started with `--webui-dist`; API routes retain precedence
over the SPA fallback. Production API/MCP/Tunnel/Connector cutover remains a
separate post-merge operation; see
`docs/runbooks/phase-c-mcp-http-cutover.md`.

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
