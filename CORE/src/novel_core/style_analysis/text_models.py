from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StyleDocumentRecord:
    id: int
    kind: str
    reference_episode_id: int | None
    project_work_id: int | None
    project_episode_id: int | None
    current_text_revision_id: int | None
    current_structure_revision_id: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class TextRevisionRecord:
    id: int
    document_id: int
    revision_no: int
    source_snapshot_id: int | None
    project_draft_id: int | None
    raw_text: str
    canonical_text: str
    raw_sha256: str
    canonical_sha256: str
    normalization_input_fingerprint: str
    normalizer_id: str
    normalizer_version: int
    metadata_json: str
    created_at: str
