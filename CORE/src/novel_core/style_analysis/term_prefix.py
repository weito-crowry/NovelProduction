from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TermPrefixEntry:
    episode_id: int
    episode_order: int
    document_id: int
    text_revision_id: int
    structure_revision_id: int
    term_run_id: int
