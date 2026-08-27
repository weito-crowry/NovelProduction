# NovelProduction

NovelProduction is the repository for the novel-production system. It is
organized as a monorepo so shared domain logic, the MCP adapter, future API and
web components, the story database, and project documentation can evolve
together.

## Directory structure

```text
CORE/      shared domain, database, and application services
MCP/       MCP adapter and stdio runtime
API/       reserved for the Phase B HTTP API
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

The Phase B HTTP API and Phase D WEBUI are not implemented yet. MCP will move
behind that API in a later phase; this extraction intentionally keeps the
current MCP runtime direct-to-CORE.

## Data ownership

`data/` belongs to NovelProduction as a whole rather than to the MCP component.
The planned SQLite database will be the canonical source of truth for story
data; export formats such as Markdown or HTML will remain derived outputs.
