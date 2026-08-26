# Novel Production MCP

This directory is the Novel Production MCP component of the NovelProduction
monorepo.

## Current status

Phase 1 foundation implemented. This directory contains the SQLite lifecycle,
immutable Phase 1 migrations, explicit `novel-init`, service/repository layers,
canon-aware entity mutation and audit decisions, bounded Japanese search, and
the 23-tool stdio MCP surface.

Phase 2 and Phase 3 schemas, tools, and runtime workflows are intentionally not
implemented. No repository `story.db` or generated story artifacts are part of
the project.

## Target stack

- Python 3.10+
- Official MCP Python SDK v2
- SQLite via the Python standard-library `sqlite3` module
- stdio transport first
- Tool-only MCP surface; no widget or web UI in Phases 1–3

The detailed design and phase plans are in
`../docs/superpowers/specs/` and `../docs/superpowers/plans/`.
