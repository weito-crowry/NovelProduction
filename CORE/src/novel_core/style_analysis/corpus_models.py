from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ContainerType = Literal["reference_work", "corpus"]
MeasurementTargetType = Literal["document", "scene"]
Statistic = Literal[
    "mean",
    "median",
    "p10",
    "p25",
    "p75",
    "p90",
    "stddev",
    "min",
    "max",
]
EpisodeMembershipMode = Literal["include", "exclude"]


@dataclass(frozen=True, slots=True)
class CorpusRecord:
    id: int
    name: str
    description: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CorpusWorkMembershipRecord:
    id: int
    corpus_id: int
    reference_work_id: int
    include_all_episodes: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class CorpusEpisodeMembershipRecord:
    id: int
    work_membership_id: int
    reference_episode_id: int
    mode: EpisodeMembershipMode
    created_at: str


@dataclass(frozen=True, slots=True)
class MeasurementRecord:
    id: int
    analysis_run_id: int
    structure_revision_id: int
    target_type: str
    target_id: int
    metric_name: str
    metric_version: int
    value: int | float
    sample_count: int
    created_at: str


@dataclass(frozen=True, slots=True)
class AggregateSpec:
    container_type: ContainerType
    container_id: int
    measurement_target_type: MeasurementTargetType
    filter_json: str
    metric_name: str
    metric_version: int


@dataclass(frozen=True, slots=True)
class AggregateRecord:
    id: int
    container_type: ContainerType
    container_id: int
    measurement_target_type: MeasurementTargetType
    filter_json: str
    metric_name: str
    metric_version: int
    statistic: Statistic
    aggregate_policy_version: int
    value_real: float
    source_measurement_count: int
    sample_count: int
    work_count: int
    skipped_target_count: int
    filter_state_fingerprint: str | None
    input_fingerprint: str
    warning_json: str
    created_at: str
    stale: bool = False


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    id: int
    name: str
    description: str
    source_corpus_id: int | None
    status: Literal["draft", "active", "archived"]
    active_version_id: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProfileVersionRecord:
    id: int
    profile_id: int
    version_no: int
    parent_version_id: int | None
    profile_generation_policy_version: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class StyleRuleRecord:
    id: int
    profile_version_id: int
    target_scope: Literal["document", "scene", "character"]
    scope_selector_json: str
    metric_name: str
    metric_version: int
    preferred_value: float | None
    min_value: float | None
    max_value: float | None
    weight: float
    enabled: bool
    severity_policy: Literal["standard"]
    source_kind: Literal["corpus", "manual"]
    created_at: str
