# Phase D WEBUI runbook

This runbook covers the Phase D React/Vite WEBUI in development, production-
style same-origin mode, and isolated browser E2E tests.

## Development

Use a temporary or disposable data root. Do not point development work at a
stable story database.

Start the API from `API/`:

```powershell
$sandboxData = Join-Path ([System.IO.Path]::GetTempPath()) "novelproduction-api-sandbox"
Set-Location API
uv run novel-api --data-root $sandboxData --host 127.0.0.1 --port 8765
```

In another shell, start the WEBUI from `WEBUI/frontend/`:

```powershell
Set-Location WEBUI/frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Vite serves the app at `http://127.0.0.1:5173` and proxies `/api` to
`http://127.0.0.1:8765`. The browser client uses relative `/api/v1` URLs, so
no CORS setting is needed for this normal development path.

## Production-style same-origin serving

Build the frontend, then serve its `dist/` directory from FastAPI:

```powershell
Set-Location WEBUI/frontend
npm ci
npm run build
Set-Location ../../API
uv run novel-api `
  --data-root <data-root> `
  --host 127.0.0.1 `
  --port 8765 `
  --webui-dist ..\WEBUI\frontend\dist
```

FastAPI keeps `/api/v1/*` routes ahead of the SPA fallback. `/` and frontend
deep links return the built `index.html`; existing built assets are served as
assets; unknown API paths remain structured JSON 404 responses.

## Trusted-LAN warning

The API and WEBUI currently have no authentication or authorization. CSRF
protection is not designed for public Internet exposure, and this system is
not a public deployment target. Bind to localhost for local use or to a
trusted LAN only after considering the network boundary.

**Do not expose NovelProduction directly to the public Internet.**

This runbook does not define a Tunnel, Connector, or public deployment
configuration.

## Isolated Chromium E2E

From the repository root on a fresh checkout:

```powershell
Set-Location API
uv sync --all-groups
Set-Location ../WEBUI/frontend
npm ci
npm run build
npx playwright install chromium
npm run test:e2e
```

The Playwright web server starts a separate FastAPI process with
`uv run --no-sync novel-api`, a fresh OS temporary data root, a dedicated
`127.0.0.1:18765` port, and `--webui-dist dist`. Set `NOVEL_E2E_PORT` to use a
different test-only port. The server refuses an occupied port, never reuses an
existing server, and removes its temporary data root when it exits.

Because the harness intentionally uses `uv run --no-sync`, the E2E runner must
run `uv sync --all-groups` from `API/` before starting the browser tests. CI
uses the same explicit API sync before installing and building the WEBUI.

E2E tests create unique project IDs and must not use repository `data/`, stable
project `2126`, a stable API process, Tunnel, Connector, or production MCP.

## Phase D stable certification

Certification status: **PASS**.

The certified main is `026a7fcf8c42693bd01c49965dd4e9f22da51f72`. The associated
post-merge MCP CI run was `33269289541` (`push`, attempt 1), with `api`, `core`,
`invariants`, `mcp`, `webui`, and `webui-e2e` all successful.

The final stable WEBUI dogfood used stable project `2126`, a production-style
WEBUI build served by a dedicated FastAPI runtime on `127.0.0.1:18766`. Health
returned HTTP 200 with API version `v1`, the built React root returned HTTP
200, and the dedicated runtime was stopped after the run. The existing stable
API on port `8765` was not operated.

The complete read-only navigation passed for Projects, Dashboard/Work,
Structure Chapter, Structure Episode 1, Structure Scene, World, Characters,
Timeline, Information, Manuscript, and Canon/History. Read-only browser
non-GET requests were zero. The stable DB SHA-256 and mtime were unchanged
during the read-only section; the later intentional Work Save/restore writes
are excluded from that invariant.

The Episode 1 legacy compatibility regression passed: both episode endpoints
returned HTTP 200, the Episode UI and Context passed, the legacy valid JSON
object in `foreshadowing_notes_json` remained unchanged, and no automatic DB
repair write occurred. Information and Canon both returned HTTP 200 with empty
`data: []` and rendered their correct empty states without persistent loading.

The Work flow used explicit Save only: the baseline title was restored after a
temporary title round trip, with exactly two normal Work PATCH requests and no
other PATCH, POST, PUT, or DELETE requests. Final `working_title`, `genre`,
`premise`, `themes_json`, `description`, and `production_status` matched the
baseline. Emergency cleanup was not used.

The two stable-dogfood blocker fixes were PR #24 (`3ae77c11c22d89c87718819d00c2b6cdd8245488`)
for Episode legacy compatibility and PR #25
(`026a7fcf8c42693bd01c49965dd4e9f22da51f72`) for Information/Canon empty
states. Existing stable API, port `8765`, Tunnel, Connector, production MCP,
and migrations `001`–`004` were untouched; migration `005` remains absent and
the MCP contract remains 59 tools.
