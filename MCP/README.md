# Novel Production MCP

This directory is the Novel Production MCP component of the NovelProduction
monorepo.

## Current status

Design and implementation planning phase. No MCP server, SQLite schema,
migration SQL, service, repository, tool handler, or test implementation is
included in this initial commit.

## Target stack

- Python 3.10+
- Official MCP Python SDK v2
- SQLite via the Python standard-library `sqlite3` module
- stdio transport first
- Tool-only MCP surface; no widget or web UI in Phases 1–3

The detailed design and phase plans are in
`../docs/superpowers/specs/` and `../docs/superpowers/plans/`.
