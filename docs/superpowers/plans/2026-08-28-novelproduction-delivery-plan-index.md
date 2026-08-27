# NovelProduction CORE/API/WEBUI Delivery Plan Index

> **For agentic workers:** Each delivery phase has its own implementation plan. Do not execute a later phase by extrapolating from the architecture spec alone; use the phase-specific plan once it exists.

**Architecture spec:** `docs/superpowers/specs/2026-08-28-novelproduction-webui-architecture-design.md`

**Parent tracking issue:** #6

## Delivery order

1. **Phase A — CORE extraction**
   - Plan: `docs/superpowers/plans/2026-08-28-novelproduction-phase-a-core-extraction.md`
   - Exit state: reusable `novel_core`, MCP still CORE-direct, migrations 001–004 owned by CORE.

2. **Phase B — API foundation**
   - Plan: to be written after Phase A implementation/review, against the actual extracted CORE interfaces.
   - Exit state: FastAPI `/api/v1`, project discovery/create/archive, fine-grained API, aggregated view API, request-scoped SQLite connections.

3. **Phase C — MCP HTTP adapter**
   - Plan: to be written after Phase B API contract is implemented/reviewed.
   - Exit state: existing MCP surface adapted to HTTP, explicit `project_id` on all project-scoped tools, no SQLite fallback.

4. **Phase D — WEBUI**
   - Plan: to be written after Phase B API contract is stable enough for UI work.
   - Exit state: React/Vite UI covering the Phase 1–3 data surface with explicit save, conflict comparison, project switching, and production static serving through FastAPI.

5. **Phase E — Structured draft editor**
   - Plan: to be written after the basic WEBUI CRUD/editor shell is stable.
   - Exit state: NovelProduction Document Schema v1, migration 005, deterministic plain-text rendering, TipTap adapter, block metadata editing, append-only structured draft revisions.

## Planning rule

The architecture spec fixes dependency direction and cross-phase contracts. Phase-specific plans are written just before implementation so they can reference the real interfaces produced by the prior phase rather than guessing file names or signatures in advance.
