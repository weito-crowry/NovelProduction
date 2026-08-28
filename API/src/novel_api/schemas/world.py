from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorldFactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    valid_from: str | None = None
    valid_to: str | None = None
    topic_key: str | None = None
    category: str = "general"
    title: str | None = None
    details_json: Any = Field(default_factory=dict)
    importance: int = 0


class WorldFactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    expected_version: int
    reason: str | None = None
    topic_key: str | None = None
    category: str | None = None
    title: str | None = None
    details_json: Any | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    importance: int | None = None
