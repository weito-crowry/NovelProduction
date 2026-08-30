from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DraftMetadataAttrs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: int | None = Field(default=None, ge=1)
    speaker_character_id: int | None = Field(default=None, ge=1)
    heading_level: int | None = Field(default=None, ge=1, le=3)


class DraftMetadataPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attrs: DraftMetadataAttrs | None = None
    annotations: dict[str, Any] | None = None
    remove_annotations: list[str] | None = Field(default=None, min_length=1)


class DraftSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plain_text: str | None = None
    html: str | None = None
    metadata_updates: dict[str, DraftMetadataPatch] | None = None
    restore_revision: int | None = Field(default=None, ge=1)
    expected_parent_draft_id: int | None = Field(default=None, ge=1)
    source_agent: str | None = Field(default=None, min_length=1, max_length=120)
    change_summary: str = Field(default="", max_length=1000)
