from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from novel_core.style_analysis.fingerprints import JsonObject

DependencyMode: TypeAlias = Literal[  # noqa: UP040
    "complete", "subject_partial_allowed"
]
JobType: TypeAlias = Literal[  # noqa: UP040
    "analyze_document",
    "analyze_reference_work",
    "recompute_aggregate",
    "run_lint",
]
RunStatus: TypeAlias = Literal[  # noqa: UP040
    "running", "succeeded", "partial", "failed", "cancelled"
]


@dataclass(frozen=True, slots=True)
class DependencySpec:
    analyzer_id: str
    mode: DependencyMode


class Analyzer(Protocol):
    id: str
    version: int
    deterministic: bool | None
    cacheable: bool
    dependencies: tuple[DependencySpec, ...]
    state_inputs: tuple[str, ...]
    policy_inputs: tuple[str, ...]
    input_scope: str | None

    def run(self, context: object) -> object: ...


@dataclass(frozen=True, slots=True)
class AnalyzerDefinition:
    id: str
    version: int
    deterministic: bool | None
    cacheable: bool
    dependencies: tuple[DependencySpec, ...]
    state_inputs: tuple[str, ...]
    policy_inputs: tuple[str, ...]
    input_scope: str | None


@dataclass(frozen=True, slots=True)
class AnalysisPolicy:
    version: int = 1
    entity_resolution_auto_merge: float = 0.90
    term_resolution_auto_merge: float = 0.90
    speaker_effective: float = 0.85
    term_explanation_effective: float = 0.85
    scene_label_effective: float = 0.80
    block_semantic_effective: float = 0.75
    pov_effective: float = 0.80
    scene_boundary_auto_apply: float = 0.85
    scene_boundary_candidate_min: float = 0.60

    def input_values(self, keys: tuple[str, ...]) -> JsonObject:
        values: JsonObject = {}
        for key in sorted(keys):
            value = getattr(self, key, None)
            if key not in self.__dataclass_fields__ or not isinstance(
                value, (int, float)
            ):
                raise ValueError(f"Unknown analysis policy input: {key}")
            values[key] = value
        return values
