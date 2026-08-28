from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CharacterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    character_key: str | None = None
    entity_type: str = "human"
    description: str = ""
    birth_date: str | None = None
    death_date: str | None = None
    physical_description: str = ""
    occupation: str = ""
    core_beliefs: str = ""
    goals: str = ""
    fears: str = ""
    personality: str = ""
    speech_style: str = ""
    ai_attitude: str = ""
    genetic_modification_attitude: str = ""
    private_notes: str = ""
    profile_json: Any = Field(default_factory=dict)


class CharacterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    display_name: str | None = None
    description: str | None = None
    reason: str | None = None
    character_key: str | None = None
    entity_type: str | None = None
    birth_date: str | None = None
    death_date: str | None = None
    physical_description: str | None = None
    occupation: str | None = None
    core_beliefs: str | None = None
    goals: str | None = None
    fears: str | None = None
    personality: str | None = None
    speech_style: str | None = None
    ai_attitude: str | None = None
    genetic_modification_attitude: str | None = None
    private_notes: str | None = None
    profile_json: Any | None = None


class RelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_character_id: int
    target_character_id: int
    relationship_type: str
    description: str = ""
    valid_from_episode_id: int | None = None
    valid_to_episode_id: int | None = None


class RelationshipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    relationship_type: str
    description: str | None = None
    reason: str | None = None
    valid_from_episode_id: int | None = None
    valid_to_episode_id: int | None = None
    clear_valid_from: bool = False
    clear_valid_to: bool = False
