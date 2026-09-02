from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExternalDocumentTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["document"]
    document_id: int = Field(gt=0)
    text_revision_id: int = Field(gt=0)
    structure_revision_id: int | None = Field(default=None, gt=0)


class ExternalReferenceWorkTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["reference_work"]
    reference_work_id: int = Field(gt=0)


class ExternalProjectEpisodeTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["project_episode"]
    episode_id: int = Field(gt=0)
    draft_id: int = Field(gt=0)


ExternalAnalysisTarget = Annotated[
    ExternalDocumentTarget | ExternalReferenceWorkTarget | ExternalProjectEpisodeTarget,
    Field(discriminator="kind"),
]


class ExternalAnalysisStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: ExternalAnalysisTarget
    executor_model_id: str = Field(min_length=1)
    rebuild_structure: bool = False


class ExternalAnalysisSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_task_version: int = Field(ge=1)
    executor_model_id: str = Field(min_length=1)
    response: dict[str, Any]


class ExternalAnalysisCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_session_version: int = Field(ge=1)
