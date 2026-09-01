from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StructureRevisionRecord:
    id: int
    text_revision_id: int
    revision_no: int
    segmenter_id: str
    segmenter_version: int
    source_kind: str
    parent_structure_revision_id: int | None
    fingerprint: str
    created_at: str
