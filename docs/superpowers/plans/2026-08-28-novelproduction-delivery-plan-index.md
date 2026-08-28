# NovelProduction CORE/API/WEBUI Delivery Plan Index

> **For agentic workers:** Each delivery phase has its own implementation plan. Do not execute a later phase by extrapolating from the architecture spec alone; use the phase-specific plan once it exists.

**Architecture spec:** `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

**Parent tracking issue:** #6

## Delivery order

1. **Phase A — CORE extraction**
   - Plan: `docs/superpowers/plans/2026-08-28-novelproduction-phase-a-core-extraction.md`
   - Status: complete. PR #12 merged; post-merge invariant follow-up PR #13 merged and main CI green.
   - Exit state: reusable `novel_core`, MCP still CORE-direct, migrations 001–004 owned by CORE.

2. **Phase B — API foundation**
   - Plan: `docs/superpowers/plans/2026-08-28-novelproduction-phase-b-api-foundation.md`
   - Status: complete. PR #14 merged as `dd2bc4acf39a64f1bc04be1be693ee8b50840c6d`; merge-to-main CI green; Issue #8 closed.
   - Exit state: FastAPI `/api/v1`, project discovery/create/archive, fine-grained Phase 1–3 API, aggregated view API, request-scoped SQLite connections.

3. **Phase C — MCP HTTP adapter**
   - Plan: `docs/superpowers/plans/2026-08-28-novelproduction-phase-c-mcp-http-adapter.md`
   - Status: ready for implementation under Issue #9.
   - Exit state: 55 existing project-data MCP tools adapted to HTTP with required explicit `project_id`, four project-management tools added (59 total), no SQLite/CORE fallback, post-merge Connector/Tunnel/API dogfood completed.

4. **Phase D — WEBUI**
   - Plan: to be written after the Phase C MCP contract is implemented/reviewed so the stable API and project identity semantics are fixed for both clients.
   - Exit state: React/Vite UI covering the Phase 1–3 data surface with explicit save, conflict comparison, project switching, and production static serving through FastAPI.

5. **Phase E — Structured draft editor**
   - Plan: to be written after the basic WEBUI CRUD/editor shell is stable.
   - Exit state: NovelProduction Document Schema v1, migration 005, deterministic plain-text rendering, TipTap adapter, block metadata editing, append-only structured draft revisions.

## Planning rule

The architecture spec fixes dependency direction and cross-phase contracts. Phase-specific plans are written just before implementation so they can reference the real interfaces produced by the prior phase rather than guessing file names or signatures in advance.
