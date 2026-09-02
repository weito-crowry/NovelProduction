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


@dataclass(frozen=True, slots=True)
class SceneRecord:
    id: int
    structure_revision_id: int
    order_index: int
    start_cp: int
    end_cp: int


@dataclass(frozen=True, slots=True)
class BlockRecord:
    id: int
    structure_revision_id: int
    scene_id: int | None
    order_index: int
    paragraph_index: int
    block_type: str
    start_cp: int
    end_cp: int


@dataclass(frozen=True, slots=True)
class SentenceRecord:
    id: int
    block_id: int
    order_index: int
    start_cp: int
    end_cp: int
