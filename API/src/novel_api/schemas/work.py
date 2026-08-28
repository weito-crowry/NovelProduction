from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_title: str
    expected_version: int
    genre: str | None = None
    premise: str | None = None
    themes_json: Any | None = None
    description: str | None = None
    production_status: str | None = None
