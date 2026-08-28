from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TimelineParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: int
    role: str


class TimelineEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    event_date: str | None = None
    participants: list[TimelineParticipant] = Field(default_factory=list)
    event_key: str | None = None
    time_start: str | None = None
    time_end: str | None = None
    date_precision: str | None = None
    date_display: str | None = None
    description: str = ""
    category: str = "general"
    location_world_fact_id: int | None = None
    cause_summary: str = ""
    consequence_summary: str = ""
    importance: int = 0


class TimelineEventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    new_date: str | None = None
    participants: list[TimelineParticipant] | None = None
    reason: str | None = None
    time_start: str | None = None
    time_end: str | None = None
    date_precision: str | None = None
    date_display: str | None = None
    description: str | None = None
    category: str | None = None
    location_world_fact_id: int | None = None
    cause_summary: str | None = None
    consequence_summary: str | None = None
    importance: int | None = None


class TimelineMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    new_date: str
    reason: str | None = None


class TimelineRelationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int
    target_id: int
    relation_type: str
