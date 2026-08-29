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
   - Status: complete. PR #15 MCP HTTP adapter merged; PR #16 SQLite read-only GET path merged; PR #17 read-only certification semantics merged. Post-merge Connector/Tunnel/API read-only dogfood, filesystem invariance gate, `BACKEND_UNAVAILABLE` fail-closed probe, stale `VERSION_CONFLICT`, controlled write, and restore all passed. Issue #9 closed as completed.
   - Exit state: 55 existing project-data MCP tools adapted to HTTP with required explicit `project_id`, four project-management tools added (59 total), no SQLite/CORE fallback, stable Connector/Tunnel/API dogfood completed.

4. **Phase D — WEBUI**
   - Plan: `docs/superpowers/plans/2026-08-29-novelproduction-phase-d-webui.md`
   - Status: complete. D1–D5 implementation and stable-dogfood blocker follow-ups PR #24 and #25 are merged; certified main is `026a7fcf8c42693bd01c49965dd4e9f22da51f72`, main CI is green, and final stable WEBUI dogfood passed. Issue #10 remains open until this bookkeeping record is reviewed and merged.
   - Exit state: React/Vite UI covering the Phase 1–3 data surface with explicit save, conflict comparison, project switching, production static serving through FastAPI, browser E2E, and certified stable dogfood.

5. **Phase E — Structured draft editor**
   - Plan: to be written after the basic WEBUI CRUD/editor shell is stable.
   - Status: not started. Eligible to begin after Phase D bookkeeping is merged and Issue #10 is closed.
   - Exit state: NovelProduction Document Schema v1, migration 005, deterministic plain-text rendering, TipTap adapter, block metadata editing, append-only structured draft revisions.

## Planning rule

The architecture spec fixes dependency direction and cross-phase contracts. Phase-specific plans are written just before implementation so they can reference the real interfaces produced by the prior phase rather than guessing file names or signatures in advance.
