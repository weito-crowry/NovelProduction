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
    DependencyRunExpectation,
    RunStatus,
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
        dependency_expectations: tuple[DependencyRunExpectation, ...] = (),
        prompt_id: str | None = None,
        prompt_version: int | None = None,
        model_provider: str | None = None,
        model_id: str | None = None,
    ) -> AnalysisRunRecord | None:
        analyzer = self._analyzers.get(analyzer_id)
        if analyzer is None or analyzer_version != getattr(analyzer, "version", None):
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
        if not self._dependencies_are_current(
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            requested_dependencies=requested_dependencies,
            expected_dependencies=expected_dependencies,
            dependency_expectations=dependency_expectations,
        ):
            return None
        canonical_config = _canonical_config_json(config_json)
        for statuses in (("succeeded",), ("partial",)):
            for candidate in self._repository.runs(
                document_id=document_id,
                analyzer_id=analyzer_id,
                analyzer_version=analyzer_version,
                text_revision_id=text_revision_id,
                structure_revision_id=structure_revision_id,
                statuses=statuses,
            ):
                if self._run_matches(
                    candidate,
                    analyzer_id=analyzer_id,
                    document_id=document_id,
                    text_revision_id=text_revision_id,
                    structure_revision_id=structure_revision_id,
                    analyzer_version=analyzer_version,
                    config_json=canonical_config,
                    state_fingerprint=state_fingerprint,
                    policy_input_fingerprint=policy_input_fingerprint,
                    dependency_runs=requested_dependencies,
                    prompt_id=prompt_id,
                    prompt_version=prompt_version,
                    model_provider=model_provider,
                    model_id=model_id,
                ):
                    return candidate
        return None

    def resolve_cache_hit(
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
        model_provider: str | None,
        model_id: str | None,
        prompt_id: str | None = None,
        prompt_version: int | None = None,
        dependency_expectations: tuple[DependencyRunExpectation, ...] = (),
    ) -> AnalysisRunRecord | None:
        analyzer = self._analyzers.get(analyzer_id)
        if (
            analyzer is None
            or analyzer_version != getattr(analyzer, "version", None)
            or not getattr(analyzer, "cacheable", False)
        ):
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
        if not self._dependencies_are_current(
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            requested_dependencies=requested_dependencies,
            expected_dependencies=expected_dependencies,
            dependency_expectations=dependency_expectations,
        ):
            return None
        fingerprint = execution_fingerprint(
            analyzer_id=analyzer_id,
            analyzer_version=analyzer_version,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            config=config_json,
            state_fingerprint=state_fingerprint,
            policy_input_fingerprint=policy_input_fingerprint,
            dependency_runs=requested_dependencies,
            model_provider=model_provider,
            model_id=model_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
        for candidate in self._repository.succeeded_runs(
            document_id=document_id,
            analyzer_id=analyzer_id,
            analyzer_version=analyzer_version,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
        ):
            if candidate.fingerprint == fingerprint and self._run_matches(
                candidate,
                analyzer_id=analyzer_id,
                document_id=document_id,
                text_revision_id=text_revision_id,
                structure_revision_id=structure_revision_id,
                analyzer_version=analyzer_version,
                config_json=_canonical_config_json(config_json),
                state_fingerprint=state_fingerprint,
                policy_input_fingerprint=policy_input_fingerprint,
                dependency_runs=requested_dependencies,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
            ):
                return candidate
        return None

    def _dependencies_are_current(
        self,
        *,
        document_id: int,
        text_revision_id: int,
        structure_revision_id: int,
        requested_dependencies: tuple[tuple[str, int], ...],
        expected_dependencies: tuple[tuple[str, DependencyMode], ...],
        dependency_expectations: tuple[DependencyRunExpectation, ...],
    ) -> bool:
        if len(requested_dependencies) != len(dependency_expectations):
            return not requested_dependencies
        expectations = {
            (expectation.analyzer_id, expectation.run_id): expectation
            for expectation in dependency_expectations
        }
        if len(expectations) != len(dependency_expectations):
            return False
        modes = dict(expected_dependencies)
        for dependency_id, dependency_run_id in requested_dependencies:
            expectation = expectations.get((dependency_id, dependency_run_id))
            analyzer = self._analyzers.get(dependency_id)
            if expectation is None or analyzer is None:
                return False
            dependency = self._repository.get_run(dependency_run_id)
            if (
                dependency is None
                or dependency.analyzer_id != dependency_id
                or not self._run_matches(
                    dependency,
                    analyzer_id=dependency_id,
                    document_id=document_id,
                    text_revision_id=text_revision_id,
                    structure_revision_id=structure_revision_id,
                    analyzer_version=getattr(analyzer, "version", -1),
                    config_json=_canonical_config_json(expectation.config_json),
                    state_fingerprint=expectation.state_fingerprint,
                    policy_input_fingerprint=expectation.policy_input_fingerprint,
                    dependency_runs=None,
                    prompt_id=expectation.prompt_id,
                    prompt_version=expectation.prompt_version,
                )
            ):
                return False
            allowed_statuses: tuple[RunStatus, ...] = ("succeeded",)
            if modes[dependency_id] == "subject_partial_allowed":
                allowed_statuses = ("succeeded", "partial")
            current = self._repository.runs(
                document_id=document_id,
                analyzer_id=dependency_id,
                analyzer_version=getattr(analyzer, "version", -1),
                text_revision_id=text_revision_id,
                structure_revision_id=structure_revision_id,
                statuses=allowed_statuses,
            )
            current = tuple(
                run
                for run in current
                if self._run_matches(
                    run,
                    analyzer_id=dependency_id,
                    document_id=document_id,
                    text_revision_id=text_revision_id,
                    structure_revision_id=structure_revision_id,
                    analyzer_version=getattr(analyzer, "version", -1),
                    config_json=_canonical_config_json(expectation.config_json),
                    state_fingerprint=expectation.state_fingerprint,
                    policy_input_fingerprint=expectation.policy_input_fingerprint,
                    dependency_runs=None,
                    prompt_id=expectation.prompt_id,
                    prompt_version=expectation.prompt_version,
                )
            )
            if modes[dependency_id] == "subject_partial_allowed":
                succeeded = tuple(run for run in current if run.status == "succeeded")
                current = succeeded or tuple(
                    run for run in current if run.status == "partial"
                )
            if not current or current[0].id != dependency_run_id:
                return False
        return True

    @staticmethod
    def _run_matches(
        candidate: AnalysisRunRecord,
        *,
        analyzer_id: str,
        document_id: int,
        text_revision_id: int,
        structure_revision_id: int,
        analyzer_version: int,
        config_json: str,
        state_fingerprint: str | None,
        policy_input_fingerprint: str | None,
        dependency_runs: tuple[tuple[str, int], ...] | None,
        prompt_id: str | None,
        prompt_version: int | None,
        model_provider: str | None = None,
        model_id: str | None = None,
    ) -> bool:
        return (
            candidate.analyzer_id == analyzer_id
            and candidate.document_id == document_id
            and candidate.text_revision_id == text_revision_id
            and candidate.structure_revision_id == structure_revision_id
            and candidate.analyzer_version == analyzer_version
            and _canonical_config_json(candidate.config_json) == config_json
            and candidate.state_fingerprint == state_fingerprint
            and candidate.policy_input_fingerprint == policy_input_fingerprint
            and (
                dependency_runs is None or candidate.dependency_runs == dependency_runs
            )
            and candidate.prompt_id == prompt_id
            and candidate.prompt_version == prompt_version
            and (model_provider is None or candidate.model_provider == model_provider)
            and (model_id is None or candidate.model_id == model_id)
        )

    @staticmethod
    def _dependency_status_allowed(status: str, mode: DependencyMode) -> bool:
        if mode == "complete":
            return status == "succeeded"
        return status in {"succeeded", "partial"}


def resolve_current_run(
    runtime: AnalysisRuntime, **kwargs: object
) -> AnalysisRunRecord | None:
    return runtime.resolve_current_run(**kwargs)  # type: ignore[arg-type]


def resolve_cache_hit(
    runtime: AnalysisRuntime, **kwargs: object
) -> AnalysisRunRecord | None:
    return runtime.resolve_cache_hit(**kwargs)  # type: ignore[arg-type]
