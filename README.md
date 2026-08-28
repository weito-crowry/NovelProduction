# NovelProduction

NovelProduction is the repository for the novel-production system. It is
organized as a monorepo so shared domain logic, the MCP adapter, future API and
web components, the story database, and project documentation can evolve
together.

## Directory structure

```text
CORE/      shared domain, database, and application services
MCP/       MCP adapter and stdio runtime
API/       Phase B FastAPI HTTP API
WEBUI/     reserved for the Phase D web UI
data/      repository-wide story database location
docs/      design specifications and implementation plans
```

Phase A is implemented. `CORE/` owns the SQLite lifecycle, immutable migrations
001–004, configuration, errors, models, repositories, initialization, and
domain services. `MCP/` is the current direct adapter over CORE and preserves
the existing 55-tool stdio interface and behavior. The configured work scope
is fixed per MCP instance, and no repository story database or generated
artifacts are committed.

The Phase B HTTP API exposes the shared CORE services under `/api/v1`. MCP
remains direct-to-CORE throughout Phase B; moving MCP behind HTTP belongs to
Phase C. Its future local backend URL is
`http://127.0.0.1:8765/api/v1`. FastAPI static serving for WEBUI is deferred to
Phase D.

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
