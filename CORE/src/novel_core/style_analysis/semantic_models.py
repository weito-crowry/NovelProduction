from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnnotationRecord:
    id: int
    annotation_type: str
    subject_type: str
    subject_id: int
    value_json: str
    confidence: float | None
    analysis_run_id: int
    start_cp: int | None
    end_cp: int | None
    created_at: str


SCENE_FUNCTIONS = frozenset(
    {
        "daily",
        "setup",
        "dialogue",
        "exposition",
        "meeting",
        "investigation",
        "travel",
        "introspection",
        "conflict",
        "action",
        "transition",
        "reveal",
        "payoff",
        "other",
        "unclear",
    }
)
SCENE_TONES = frozenset(
    {
        "neutral",
        "calm",
        "humorous",
        "warm",
        "tense",
        "emotional",
        "ominous",
        "sad",
        "excited",
        "other",
        "unclear",
    }
)
SCENE_PACES = frozenset({"slow", "medium", "fast", "unclear"})
SCENE_INFORMATION_LOADS = frozenset({"low", "medium", "high", "unclear"})
SCENE_INTERACTIONS = frozenset(
    {"solo", "dialogue", "group_dialogue", "crowd", "mixed", "unclear"}
)
BLOCK_PRIMARY_LABELS = frozenset(
    {
        "action",
        "description",
        "exposition",
        "psychology",
        "transition",
        "other",
        "unclear",
    }
)
POV_MODES = frozenset(
    {"first_person", "third_limited", "omniscient", "objective", "unclear"}
)
BOUNDARY_REASONS = frozenset(
    {"time_shift", "location_shift", "pov_shift", "context_reset"}
)
