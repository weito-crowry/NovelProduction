from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

CanonStatus = Literal["idea", "draft", "canon", "deprecated"]
ProductionStatus = Literal["planned", "outlined", "drafting", "revising", "final"]
ReferenceType = Literal["character", "world_fact", "timeline_event", "information"]


class ChapterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str = ""
    purpose: str = ""
    production_status: ProductionStatus = "planned"
    canon_status: CanonStatus = "draft"


class ChapterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    summary: str | None = None
    purpose: str | None = None
    production_status: ProductionStatus | None = None
    canon_status: CanonStatus | None = None
    reason: str | None = None


class Reorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_position: int
    expected_version: int


class EpisodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str = ""
    purpose: str = ""
    foreshadowing_notes: Any = None
    production_status: ProductionStatus = "planned"
    canon_status: CanonStatus = "draft"


class EpisodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    summary: str | None = None
    purpose: str | None = None
    foreshadowing_notes: Any = None
    production_status: ProductionStatus | None = None
    canon_status: CanonStatus | None = None
    reason: str | None = None


class SceneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str = ""
    purpose: str = ""
    production_status: ProductionStatus = "planned"
    canon_status: CanonStatus = "draft"


class SceneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    summary: str | None = None
    purpose: str | None = None
    production_status: ProductionStatus | None = None
    canon_status: CanonStatus | None = None
    reason: str | None = None


class EpisodeReferenceAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: ReferenceType
    target_id: int
    role: str = "participant"


class CharacterStateSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    physical_state: str | None = None
    emotional_state: str | None = None
    beliefs_json: Any = None
    location_world_fact_id: int | None = None
    state_json: Any = None
    expected_version: int | None = None
