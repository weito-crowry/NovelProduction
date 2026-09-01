from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class StyleImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reused_existing: bool
    reference_work_id: int
    source_id: int


class ReferenceWorkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_work_id: int
    source_id: int
    source_type: str
    title: str
    author_name: str | None
    episode_count: int
    created_at: str


class ReferenceEpisodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_episode_id: int
    reference_work_id: int
    title: str
    order_index: int
    style_document_id: int | None
    current_text_revision_id: int | None
    current_structure_revision_id: int | None
    current_structure_kind: str | None
    analysis_status: dict[str, Any]
