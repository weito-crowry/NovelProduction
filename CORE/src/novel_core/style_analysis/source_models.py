from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from novel_core.style_analysis.fingerprints import JsonObject

SourceType = Literal["text", "html_file", "epub"]


@dataclass(frozen=True, slots=True)
class SourceEpisodeInput:
    external_episode_id: str
    title: str
    order_index: int
    raw_text: str
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class SourceWorkInput:
    title: str
    author_name: str | None
    metadata: JsonObject
    episodes: tuple[SourceEpisodeInput, ...]


@dataclass(frozen=True, slots=True)
class StyleSourceRecord:
    id: int
    source_type: SourceType
    external_work_id: str
    original_filename: str
    adapter_id: str
    adapter_version: int
    created_at: str


@dataclass(frozen=True, slots=True)
class StyleSourceSnapshotRecord:
    id: int
    source_id: int
    filename: str
    media_type: str
    payload_sha256: str
    raw_payload: bytes
    metadata_json: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ReferenceWorkRecord:
    id: int
    source_id: int
    source_type: SourceType
    external_work_id: str
    title: str
    author_name: str | None
    metadata_json: str
    created_at: str
    updated_at: str
    episode_count: int


@dataclass(frozen=True, slots=True)
class ReferenceEpisodeRecord:
    id: int
    reference_work_id: int
    external_episode_id: str
    title: str
    order_index: int
    latest_snapshot_id: int
    metadata_json: str
    created_at: str
    updated_at: str
    style_document_id: int | None
    current_text_revision_id: int | None
    current_structure_revision_id: int | None
    current_structure_kind: str | None
    current_text: str | None
    document_metadata_json: str | None


@dataclass(frozen=True, slots=True)
class SourceImportResult:
    source: StyleSourceRecord
    snapshot: StyleSourceSnapshotRecord
    work: ReferenceWorkRecord
