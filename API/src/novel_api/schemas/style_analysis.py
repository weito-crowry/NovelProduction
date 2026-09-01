from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    model_validator,
)


class StyleImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reused_existing: bool
    reference_work_id: int
    source_id: int


class ReferenceWorkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_work_id: int
    source_id: int
    source_type: str
    title: str
    author_name: str | None
    episode_count: int
    created_at: str


class ReferenceEpisodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_episode_id: int
    reference_work_id: int
    title: str
    order_index: int
    style_document_id: int | None
    current_text_revision_id: int | None
    current_structure_revision_id: int | None
    current_structure_kind: str | None
    analysis_status: dict[str, Any]


class StyleAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_revision_id: int
    structure_revision_id: int | None = None
    preset: Literal["deterministic", "full"] = "full"
    rebuild_structure: bool = False

    @model_validator(mode="after")
    def validate_structure_rebuild(self) -> StyleAnalyzeRequest:
        if self.structure_revision_id is not None and self.rebuild_structure:
            raise ValueError("STRUCTURE_REBUILD_CONFLICT")
        return self


class StyleWorkAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: Literal["deterministic", "full"] = "full"
    rebuild_structure: bool = False


class StyleJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int
    job_type: str
    status: str
    progress: dict[str, int | None]
    result: dict[str, Any]
    warnings: list[Any]
    error_code: str | None
    error_message: str | None


class CorpusCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""


class CorpusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class CorpusWorkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_work_id: int
    include_all_episodes: bool = True


class CorpusEpisodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["include", "exclude"]


class AggregateRecomputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_target_type: Literal["document", "scene"]
    filter: dict[str, Any] = Field(default_factory=dict)
    metric_names: list[str] = Field(min_length=1)


class ProfileAggregateGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_aggregate_id: int
    min_aggregate_id: int
    max_aggregate_id: int


class ProfileRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_scope: Literal["document", "scene", "character"]
    scope_selector: dict[str, Any]
    metric_name: str
    metric_version: int
    preferred_value: StrictInt | StrictFloat | None = None
    min_value: StrictInt | StrictFloat | None = None
    max_value: StrictInt | StrictFloat | None = None
    weight: StrictInt | StrictFloat = 1.0
    enabled: bool = True
    severity_policy: Literal["standard"] = "standard"


class ProfileFromCorpusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: int
    name: str
    description: str = ""
    rules: list[ProfileAggregateGroupRequest]


class ProfileManualRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    rules: list[ProfileRuleRequest]


class ProfileNewVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_version_no: int
    rules: list[ProfileRuleRequest]


class ProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class ProfileActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_no: int
