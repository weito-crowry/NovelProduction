# Phase C MCP HTTP cutover runbook

This runbook is for the post-merge review and dogfood operation. The Phase C
implementation PR does not perform a production cutover: it does not access
the stable story database, start or stop the production API/MCP process, or
change the Cloudflare Tunnel or ChatGPT Connector configuration.

## Post-merge procedure

1. Update the local checkout to the merged Phase C revision.

   ```powershell
   git fetch origin
   git switch main
   git pull --ff-only origin main
   ```

2. Start `novel-api` with the intended data root and the established port. Use
   `127.0.0.1:8765` for local-only dogfood; use `0.0.0.0:8765` only when the
   trusted-LAN deployment explicitly requires it.

   ```powershell
   Set-Location API
   uv run novel-api --data-root <intended-data-root> --host 127.0.0.1 --port 8765
   ```

3. In a separate shell, verify API readiness and project discovery.

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/api/v1/health
   Invoke-RestMethod http://127.0.0.1:8765/api/v1/projects
   ```

4. Start MCP with the API URL. The CLI takes precedence over
   `NOVEL_API_URL`; otherwise the default is `http://127.0.0.1:8765`.

   ```powershell
   Set-Location MCP
   $env:NOVEL_API_URL = "http://127.0.0.1:8765"
   uv run novel-mcp
   ```

   An explicit CLI override is equivalent:

   ```powershell
   uv run novel-mcp --api-url http://127.0.0.1:8765
   ```

5. Refresh or reconnect the ChatGPT Connector. Confirm that the MCP server
   exposes exactly 59 tools and that every project-scoped tool schema requires
   `project_id`. There is no project-selection or last-used-project state.

6. Run read-only dogfood in this order:

   - `project_list`
   - `project_get(project_id="<known-project>")`
   - `work_get(project_id="2126")`
   - one approved search/read operation with the same explicit project ID

   Confirm that API and MCP logs identify the same `project_id` and that the
   MCP response has `project_id` at the top level, alongside `data`, without a
   second nested project envelope.

7. Run a controlled write only when separately approved. Verify the returned
   API/MCP error details for stale versions, including `VERSION_CONFLICT`,
   before considering the write dogfood successful.

8. Keep the current Tunnel route unchanged unless the MCP process address
   actually changes. MCP must remain an HTTP client of the API; it must never
   fall back to CORE or direct SQLite access if the API is unavailable.

## Failure and rollback

If health, project discovery, schema refresh, identity checks, or dogfood
fails, stop the new MCP/API processes and restore the prior runtime process and
configuration. Do not repair, reset, migrate, vacuum, seed, or replace the
story database as a rollback mechanism. Leave the Connector and Tunnel
unchanged until the reviewed post-merge operation has passed.
