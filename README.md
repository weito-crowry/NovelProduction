# NovelProduction

NovelProduction is the repository for the future novel-production system. It is
organized as a monorepo so the MCP component and a future web component can be
developed alongside the shared story database and project documentation.

## Directory structure

```text
MCP/       Novel Production MCP component
data/      repository-wide story database location
docs/      design specifications and implementation plans
WEB/       reserved for a future web component
```

The Phase 1 MCP foundation is implemented under `MCP/`. It provides the
SQLite lifecycle and immutable Phase 1 migrations, explicit work
initialization, canon-aware CRUD for the Phase 1 entities, bounded Japanese
search, and exactly 23 stdio MCP tools. The configured work scope is fixed per
MCP instance and no repository story database or generated artifacts are
committed.

Phase 2 and Phase 3 tools and runtime workflows remain intentionally deferred;
the future web component is not implemented.

## Data ownership

`data/` belongs to NovelProduction as a whole rather than to the MCP component.
The planned SQLite database will be the canonical source of truth for story
data; export formats such as Markdown or HTML will remain derived outputs.
