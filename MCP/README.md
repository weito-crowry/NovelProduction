# Novel Production MCP

This directory is the Novel Production MCP component of the NovelProduction
monorepo.

## Current status

Phase A extraction implemented. Shared SQLite lifecycle, migrations 001–004,
configuration, errors, models, repositories, initialization, and domain
services are owned by the sibling `CORE/` package. This directory contains the
MCP adapter/runtime, compatibility facades, and the preserved 55-tool stdio
MCP surface.

The MCP runtime currently imports CORE directly. The future API boundary will
be introduced in Phase B/C; no HTTP API or WEBUI is part of this phase. No
repository `story.db` or generated story artifacts are part of the project.

## Target stack

- Python 3.10+
- Official MCP Python SDK v2
- SQLite via the Python standard-library `sqlite3` module
- stdio transport first
- Tool-only MCP surface; no widget or web UI in Phases 1–3

The detailed design and phase plans are in
`../docs/superpowers/specs/` and `../docs/superpowers/plans/`.
