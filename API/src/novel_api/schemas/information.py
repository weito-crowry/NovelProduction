from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

CanonStatus = Literal["idea", "draft", "canon", "deprecated"]
TruthStatus = Literal["true", "false", "uncertain", "subjective"]
KnowledgeState = Literal[
    "suspects", "believes", "knows", "confirmed", "doubts", "rejected"
]


class InformationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    truth_status: TruthStatus = "uncertain"
    authoring_guard: str = ""
    notes_json: Any = None
    canon_status: CanonStatus = "draft"
    importance: int = 0


class InformationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    statement: str | None = None
    truth_status: TruthStatus | None = None
    authoring_guard: str | None = None
    notes_json: Any = None
    importance: int | None = None
    canon_status: CanonStatus | None = None
    reason: str | None = None


class ReaderDisclosureSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: int
    expected_version: int | None = None


class CharacterKnowledgeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: int
    knowledge_state: KnowledgeState
    note: str = ""
    expected_version: int | None = None
