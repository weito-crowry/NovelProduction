from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CanonStatusSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    entity_id: int
    target_status: str
    expected_version: int
    reason: str | None = None
