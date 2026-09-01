from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TermPrefixEntry:
    episode_id: int
    episode_order: int
    document_id: int | None
    text_revision_id: int | None
    structure_revision_id: int | None
    term_run_id: int | None
    resolver_status: str | None = None
