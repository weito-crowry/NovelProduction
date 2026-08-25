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

The current repository contains architecture and implementation planning
artifacts only. MCP behavior, database migrations, and the web component have
not been implemented yet.

## Data ownership

`data/` belongs to NovelProduction as a whole rather than to the MCP component.
The planned SQLite database will be the canonical source of truth for story
data; export formats such as Markdown or HTML will remain derived outputs.
