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

From `WEBUI/frontend/`:

```powershell
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

E2E tests create unique project IDs and must not use repository `data/`, stable
project `2126`, a stable API process, Tunnel, Connector, or production MCP.
