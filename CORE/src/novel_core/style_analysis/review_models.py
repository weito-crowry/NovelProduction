from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

ReviewItemSubject: TypeAlias = Literal[  # noqa: UP040
    "structure_revision",
    "scene",
    "block",
    "mention",
    "term_mention",
    "entity",
    "term",
]
ReviewItemStatus: TypeAlias = Literal[  # noqa: UP040
    "open", "resolved", "ignored", "superseded"
]
ReviewItemPriority: TypeAlias = Literal["normal", "high"]  # noqa: UP040
OverrideOperation: TypeAlias = Literal["set", "clear", "revert"]  # noqa: UP040
InferenceReviewStatus: TypeAlias = Literal["confirmed", "rejected"]  # noqa: UP040


@dataclass(frozen=True, slots=True)
class ReviewItemRecord:
    id: int
    document_id: int | None
    reference_work_id: int | None
    item_type: str
    subject_type: str
    subject_id: int
    analysis_run_id: int | None
    priority: str
    status: str
    reason_code: str
    evidence_json: str
    resolution_note: str | None
    version: int
    created_at: str
    resolved_at: str | None


@dataclass(frozen=True, slots=True)
class ManualOverrideRecord:
    id: int
    document_id: int | None
    reference_work_id: int | None
    subject_type: str
    subject_id: int
    field_path: str
    operation: str
    value_json: str | None
    base_analysis_run_id: int | None
    structure_revision_id: int | None
    note: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class InferenceReviewRecord:
    id: int
    document_id: int | None
    reference_work_id: int | None
    subject_type: str
    subject_id: int
    field_path: str
    analysis_run_id: int
    review_status: str
    note: str | None
    created_at: str
