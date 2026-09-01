from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TermRecord:
    id: int
    reference_work_id: int | None
    document_id: int | None
    canonical_label: str
    term_type: str
    origin: str
    created_by_run_id: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class TermAliasRecord:
    id: int
    term_id: int
    alias: str
    origin: str
    analysis_run_id: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class TermMentionRecord:
    id: int
    term_id: int
    structure_revision_id: int
    scene_id: int
    block_id: int
    start_cp: int
    end_cp: int
    surface: str
    analysis_run_id: int


TERM_TYPES = frozenset(
    {
        "world_term",
        "technology",
        "institution",
        "organization_name",
        "location_name",
        "product_name",
        "ability",
        "historical_event",
        "specialized_term",
        "other",
    }
)
NOVELTY_VALUES = frozenset(
    {"work_specific", "specialized_real_world", "common_real_world", "uncertain"}
)
