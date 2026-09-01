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


class StyleEntityCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_work_id: int | None = Field(default=None, gt=0)
    document_id: int | None = Field(default=None, gt=0)
    entity_type: Literal[
        "person",
        "organization",
        "location",
        "technology",
        "concept",
        "product",
        "event",
        "other",
    ]
    canonical_name: str

    @model_validator(mode="after")
    def validate_scope(self) -> StyleEntityCreateRequest:
        if (self.reference_work_id is None) == (self.document_id is None):
            raise ValueError("ENTITY_SCOPE_INVALID")
        return self


class StyleEntityAliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str
    alias_kind: Literal["name", "surname", "given_name", "nickname", "title", "role"]


class StyleEntityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reference_work_id: int | None
    document_id: int | None
    entity_type: str
    canonical_name: str
    origin: str
    created_by_run_id: int | None
    created_at: str


class StyleEntityAliasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    entity_id: int
    alias: str
    alias_kind: str
    origin: str
    analysis_run_id: int | None
    source_mention_id: int | None
    created_at: str


class StyleTermCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_work_id: int | None = Field(default=None, gt=0)
    document_id: int | None = Field(default=None, gt=0)
    canonical_label: str
    term_type: Literal[
        "world_term",
        "technology",
        "institution",
        "organization_name",
        "location_name",
        "product_name",
        "ability",
        "historical_event",
        "specialized_term",
        "other",
    ]

    @model_validator(mode="after")
    def validate_scope(self) -> StyleTermCreateRequest:
        if (self.reference_work_id is None) == (self.document_id is None):
            raise ValueError("TERM_SCOPE_INVALID")
        return self


class StyleTermAliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str


class StyleTermResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reference_work_id: int | None
    document_id: int | None
    canonical_label: str
    term_type: str
    origin: str
    created_by_run_id: int | None
    created_at: str


class StyleTermAliasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    term_id: int
    alias: str
    origin: str
    analysis_run_id: int | None
    created_at: str


class CharacterLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style_entity_id: int = Field(gt=0)


class CharacterLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int
    style_entity_id: int
    project_character_id: int


class StyleOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_type: str
    subject_id: int = Field(gt=0)
    field_path: str
    operation: Literal["set", "clear", "revert"]
    value: Any = None
    document_id: int | None = Field(default=None, gt=0)
    reference_work_id: int | None = Field(default=None, gt=0)
    base_analysis_run_id: int | None = Field(default=None, gt=0)
    structure_revision_id: int | None = Field(default=None, gt=0)
    note: str | None = None


class StyleOverrideResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    document_id: int | None
    reference_work_id: int | None
    subject_type: str
    subject_id: int
    field_path: str
    operation: str
    value: Any
    base_analysis_run_id: int | None
    structure_revision_id: int | None
    note: str | None
    created_at: str
    correction_class: str
    job_id: int | None = None


class InferenceReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_run_id: int = Field(gt=0)
    subject_type: str
    subject_id: int = Field(gt=0)
    field_path: str
    review_status: Literal["confirmed", "rejected"]
    note: str | None = None


class InferenceReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    document_id: int | None
    reference_work_id: int | None
    subject_type: str
    subject_id: int
    field_path: str
    analysis_run_id: int
    review_status: str
    note: str | None
    created_at: str
    correction_class: str
    job_id: int | None = None


class ReviewItemCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_type: Literal[
        "structure_revision",
        "scene",
        "block",
        "mention",
        "term_mention",
        "entity",
        "term",
    ]
    subject_id: int = Field(gt=0)
    analysis_run_id: int | None = Field(default=None, gt=0)
    priority: Literal["normal", "high"] = "normal"


class ReviewItemActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)
    note: str | None = None


class ReviewItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    document_id: int | None
    reference_work_id: int | None
    item_type: str
    subject_type: str
    subject_id: int
    analysis_run_id: int | None
    priority: str
    status: str
    reason_code: str
    evidence: dict[str, Any]
    resolution_note: str | None
    version: int
    created_at: str
    resolved_at: str | None


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
    weight: StrictInt | StrictFloat
    enabled: bool
    severity_policy: Literal["standard"]


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
