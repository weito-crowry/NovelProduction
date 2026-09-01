from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.fingerprints import (
    JsonValue,
    canonical_json_bytes,
)
from novel_core.style_analysis.runtime_models import (
    AnalysisRunRecord,
    DependencyMode,
)
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID


def _canonical_config_json(config_json: str) -> str:
    try:
        value = cast(JsonValue, json.loads(config_json))
    except json.JSONDecodeError as exc:
        raise ValidationError("CONFIG_JSON_INVALID") from exc
    return canonical_json_bytes(value).decode()


def _config_value(config: JsonValue | str) -> JsonValue:
    if not isinstance(config, str):
        return config
    try:
        return cast(JsonValue, json.loads(config))
    except json.JSONDecodeError as exc:
        raise ValidationError("CONFIG_JSON_INVALID") from exc


def execution_fingerprint(
    *,
    analyzer_id: str,
    analyzer_version: int,
    text_revision_id: int,
    structure_revision_id: int,
    config: JsonValue | str,
    state_fingerprint: str | None,
    policy_input_fingerprint: str | None,
    dependency_runs: tuple[tuple[str, int], ...],
    model_provider: str | None,
    model_id: str | None,
    prompt_id: str | None = None,
    prompt_version: int | None = None,
) -> str:
    canonical_dependencies: list[JsonValue] = [
        {"analyzer_id": dependency_id, "run_id": run_id}
        for dependency_id, run_id in sorted(dependency_runs)
    ]
    payload: dict[str, JsonValue] = {
        "analyzer_id": analyzer_id,
        "analyzer_version": analyzer_version,
        "text_revision_id": text_revision_id,
        "structure_revision_id": structure_revision_id,
        "config": _config_value(config),
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "state_fingerprint": state_fingerprint,
        "policy_input_fingerprint": policy_input_fingerprint,
        "dependency_runs": canonical_dependencies,
        "model_provider": model_provider,
        "model_id": model_id,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


create_execution_fingerprint = execution_fingerprint


class AnalysisRuntime:
    def __init__(
        self,
        repository: AnalysisRunRepository,
        *,
        analyzers: Mapping[str, object] = ANALYZERS_BY_ID,
    ) -> None:
        self._repository = repository
        self._analyzers = analyzers

    def resolve_current_run(
        self,
        *,
        document_id: int,
        analyzer_id: str,
        text_revision_id: int,
        structure_revision_id: int,
        analyzer_version: int,
        config_json: str,
        state_fingerprint: str | None,
        policy_input_fingerprint: str | None,
        dependency_runs: tuple[tuple[str, int], ...],
    ) -> AnalysisRunRecord | None:
        analyzer = self._analyzers.get(analyzer_id)
        if analyzer is None or not getattr(analyzer, "cacheable", False):
            return None
        requested_dependencies = tuple(sorted(dependency_runs))
        expected_dependencies = tuple(
            sorted(
                (dependency.analyzer_id, dependency.mode)
                for dependency in getattr(analyzer, "dependencies", ())
            )
        )
        if tuple(dependency_id for dependency_id, _ in requested_dependencies) != tuple(
            dependency_id for dependency_id, _ in expected_dependencies
        ):
            return None
        dependency_modes = {
            dependency_id: mode for dependency_id, mode in expected_dependencies
        }
        for dependency_id, dependency_run_id in requested_dependencies:
            dependency = self._repository.get_run(dependency_run_id)
            if dependency is None or dependency.analyzer_id != dependency_id:
                return None
            if not self._dependency_status_allowed(
                dependency.status, dependency_modes[dependency_id]
            ):
                return None
        canonical_config = _canonical_config_json(config_json)
        for candidate in self._repository.succeeded_runs(
            document_id=document_id,
            analyzer_id=analyzer_id,
            analyzer_version=analyzer_version,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
        ):
            if (
                _canonical_config_json(candidate.config_json) == canonical_config
                and candidate.state_fingerprint == state_fingerprint
                and candidate.policy_input_fingerprint == policy_input_fingerprint
                and candidate.dependency_runs == requested_dependencies
            ):
                return candidate
        return None

    @staticmethod
    def _dependency_status_allowed(status: str, mode: DependencyMode) -> bool:
        if mode == "complete":
            return status == "succeeded"
        return status in {"succeeded", "partial"}


def resolve_current_run(
    runtime: AnalysisRuntime, **kwargs: object
) -> AnalysisRunRecord | None:
    return runtime.resolve_current_run(**kwargs)  # type: ignore[arg-type]
