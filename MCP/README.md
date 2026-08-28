# Novel Production MCP

This directory is the Novel Production MCP component of the NovelProduction
monorepo.

## Current status

Phase C is implemented. Shared SQLite lifecycle, migrations 001–004,
configuration, errors, models, repositories, initialization, and domain
services are owned by the sibling `CORE/` package and reached at runtime only
through the `API/` HTTP service. This directory contains a stateless MCP HTTP
adapter and stdio runtime with the preserved 55 project-data tools plus four
project-management tools, for 59 tools total.

Every project-scoped call requires an explicit `project_id`; MCP does not keep
selected-project state. The adapter uses one shared `httpx.AsyncClient` per
process, validates project identity in successful responses, preserves API
error details, and fails closed when the API is unavailable. It does not import
CORE or access SQLite directly, and it has no direct-DB fallback. No repository
`story.db` or generated story artifacts are part of the project.

## Target stack

- Python 3.10+
- Official MCP Python SDK v2
- `httpx` for the API client
- stdio transport first
- Tool-only MCP surface; no widget or web UI in Phases 1–3

The detailed design and phase plans are in
`../docs/superpowers/specs/` and `../docs/superpowers/plans/`.
