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

2. Stop the old direct-MCP/runtime process before taking any database
   baseline. Confirm that no remaining process command line references the
   target `story.db`, and wait until SQLite is quiescent. A shutdown of the
   old runtime can checkpoint an already-existing WAL; that checkpoint belongs
   to the pre-cutover baseline transition, not to the new API read path.

3. Record the quiescent baseline for `story.db` and an existing
   `story.db-wal`, including content hash, size, and presence. Record
   `story.db-shm` separately as a SQLite runtime sidecar. Do not repair,
   migrate, vacuum, seed, replace, or delete any stable database while
   collecting this baseline.

4. Start `novel-api` with the intended data root and the established port. Use
   `127.0.0.1:8765` for local-only dogfood; use `0.0.0.0:8765` only when the
   trusted-LAN deployment explicitly requires it.

   ```powershell
   Set-Location API
   uv run novel-api --data-root <intended-data-root> --host 127.0.0.1 --port 8765
   ```

5. In a separate shell, verify API readiness and project discovery.

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/api/v1/health
   Invoke-RestMethod http://127.0.0.1:8765/api/v1/projects
   ```

6. Start MCP with the API URL. The CLI takes precedence over
   `NOVEL_API_URL`; otherwise the default is `http://127.0.0.1:8765`.

   ```powershell
   Set-Location MCP
   $env:NOVEL_API_URL = "http://127.0.0.1:8765"
   uv run python -m novel_mcp.mcp_server
   ```

   An explicit CLI override is equivalent:

   ```powershell
   uv run python -m novel_mcp.mcp_server --api-url http://127.0.0.1:8765
   ```

7. Refresh or reconnect the ChatGPT Connector. Confirm that the MCP server
   exposes exactly 59 tools and that every project-scoped tool schema requires
   `project_id`. There is no project-selection or last-used-project state.

8. Run read-only dogfood in this order:

   - `project_list`
   - `project_get(project_id="<known-project>")`
   - `work_get(project_id="2126")`
   - one approved search/read operation with the same explicit project ID

   Confirm that API and MCP logs identify the same `project_id` and that the
   MCP response has `project_id` at the top level, alongside `data`, without a
   second nested project envelope.

9. Compare the post-dogfood `story.db` and existing `story.db-wal` content
   hashes, sizes, and presence with the quiescent baseline. Treat SHM
   creation/deletion separately; it is a SQLite sidecar and is not by itself
   domain-data mutation. If the main DB or WAL changes, stop and investigate
   before any write dogfood.

10. Run a controlled write only when separately approved. Verify the returned
   API/MCP error details for stale versions, including `VERSION_CONFLICT`,
   before considering the write dogfood successful.

11. Keep the current Tunnel route unchanged unless the MCP process address
   actually changes. MCP must remain an HTTP client of the API; it must never
   fall back to CORE or direct SQLite access if the API is unavailable.

## Failure and rollback

If health, project discovery, schema refresh, identity checks, or dogfood
fails, stop the new MCP/API processes and restore the prior runtime process and
configuration. Do not repair, reset, migrate, vacuum, seed, or replace the
story database as a rollback mechanism. Leave the Connector and Tunnel
unchanged until the reviewed post-merge operation has passed.
