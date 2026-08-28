from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DraftSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)
    expected_parent_draft_id: int | None = Field(default=None, ge=1)
    source_agent: str | None = Field(default=None, min_length=1, max_length=120)
    change_summary: str = Field(default="", max_length=1000)
