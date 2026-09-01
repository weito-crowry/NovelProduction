from __future__ import annotations

import json
from typing import Any, cast

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.analysis_runtime import AnalysisRuntime
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.runtime_models import (
    AnalysisRunRecord,
    DependencyRunExpectation,
)
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID

PROMPT_IDS = {
    "entity-mention-extractor": "style.entity_mentions",
    "entity-resolver": "style.entity_resolution",
    "speaker-attribution": "style.speaker_attribution",
    "term-candidate-extractor": "style.term_candidates",
    "term-resolver": "style.term_resolution",
    "term-explanation-detector": "style.term_explanation",
    "scene-semantic-classifier": "style.scene_semantics",
    "block-semantic-classifier": "style.block_semantic",
    "pov-classifier": "style.pov",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def config_for_analyzer(analyzer_id: str) -> JsonValue:
    if analyzer_id == "style-metrics-basic":
        from novel_core.style_analysis.metrics import BASIC_METRIC_DEFINITIONS

        return {
            "metric_versions": {
                name: definition.version
                for name, definition in sorted(BASIC_METRIC_DEFINITIONS.items())
            }
        }
    if analyzer_id == "scene-semantic-classifier":
        return {"scene_taxonomy_version": 1}
    if analyzer_id == "block-semantic-classifier":
        return {"block_semantic_taxonomy_version": 1}
    if analyzer_id == "pov-classifier":
        return {"pov_taxonomy_version": 1}
    return {}


def state_for_analyzer(
    orchestrator: DocumentAnalysisOrchestrator,
    analyzer_id: str,
    document_id: int,
    structure_revision_id: int,
    current: dict[str, AnalysisRunRecord],
) -> JsonValue | None:
    if analyzer_id == "entity-resolver":
        return cast(
            JsonValue,
            {
                "scope": orchestrator.entities._scope(document_id),
                "entity_registry_state": orchestrator._entity_registry_state(
                    document_id
                ),
            },
        )
    if analyzer_id == "term-resolver":
        return cast(
            JsonValue,
            {
                "scope": orchestrator.terms._scope(document_id),
                "term_registry_state": orchestrator._term_registry_state(document_id),
            },
        )
    if analyzer_id in {"speaker-attribution", "pov-classifier"}:
        entity_run = current.get("entity-resolver")
        if entity_run is None:
            return None
        return cast(
            JsonValue,
            {
                "mention_resolution": orchestrator._mention_resolution_state(
                    document_id, structure_revision_id, entity_run.id
                )
            },
        )
    return None


def select_current_runs(
    catalog: Any,
    document_id: int,
    text_revision_id: int,
    structure_revision_id: int,
    analyzer_ids: tuple[str, ...],
) -> tuple[AnalysisRunRecord, ...]:
    orchestrator = DocumentAnalysisOrchestrator(
        catalog._connection,
        model_client=None,
        model_provider=None,
        model_id=None,
    )
    runtime = AnalysisRuntime(catalog._runs)
    current: dict[str, AnalysisRunRecord] = {}
    for analyzer_id in analyzer_ids:
        definition = ANALYZERS_BY_ID.get(analyzer_id)
        if definition is None:
            continue
        dependencies: list[tuple[str, int]] = []
        expectations: list[DependencyRunExpectation] = []
        dependencies_ready = True
        for dependency in definition.dependencies:
            selected_dependency = current.get(dependency.analyzer_id)
            if selected_dependency is None or (
                dependency.mode == "complete"
                and selected_dependency.status != "succeeded"
            ):
                dependencies_ready = False
                break
            dependencies.append((dependency.analyzer_id, selected_dependency.id))
            expectations.append(
                DependencyRunExpectation(
                    analyzer_id=dependency.analyzer_id,
                    run_id=selected_dependency.id,
                    config_json=selected_dependency.config_json,
                    state_fingerprint=selected_dependency.state_fingerprint,
                    policy_input_fingerprint=selected_dependency.policy_input_fingerprint,
                    prompt_id=selected_dependency.prompt_id,
                    prompt_version=selected_dependency.prompt_version,
                )
            )
        if not dependencies_ready:
            continue
        config_json = _canonical_json(config_for_analyzer(analyzer_id))
        state = state_for_analyzer(
            orchestrator,
            analyzer_id,
            document_id,
            structure_revision_id,
            current,
        )
        state_fingerprint = None if state is None else fingerprint_json(state)
        policy_input_fingerprint = (
            fingerprint_json(
                cast(
                    JsonValue,
                    orchestrator.policy.input_values(definition.policy_inputs),
                )
            )
            if definition.policy_inputs
            else None
        )
        prompt_id = PROMPT_IDS.get(analyzer_id)
        prompt_version = None if prompt_id is None else get_prompt(prompt_id).version
        selected = runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id=analyzer_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=definition.version,
            config_json=config_json,
            state_fingerprint=state_fingerprint,
            policy_input_fingerprint=policy_input_fingerprint,
            dependency_runs=tuple(dependencies),
            dependency_expectations=tuple(expectations),
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
        if selected is not None:
            current[analyzer_id] = selected
    return tuple(
        current[analyzer_id] for analyzer_id in analyzer_ids if analyzer_id in current
    )


def resolution_state_changed(
    catalog: Any,
    document_id: int,
    text_revision_id: int | None,
    structure_revision_id: int | None,
    history: tuple[AnalysisRunRecord, ...],
    current: dict[str, AnalysisRunRecord],
) -> bool:
    if text_revision_id is None or structure_revision_id is None:
        return False
    orchestrator = DocumentAnalysisOrchestrator(
        catalog._connection,
        model_client=None,
        model_provider=None,
        model_id=None,
    )
    for analyzer_id in ("entity-resolver", "term-resolver"):
        if analyzer_id in current:
            continue
        state = state_for_analyzer(
            orchestrator,
            analyzer_id,
            document_id,
            structure_revision_id,
            {},
        )
        expected = None if state is None else fingerprint_json(state)
        for run in history:
            if (
                run.analyzer_id == analyzer_id
                and run.text_revision_id == text_revision_id
                and run.structure_revision_id == structure_revision_id
                and run.status in {"succeeded", "partial"}
                and run.state_fingerprint != expected
            ):
                return True
    for run in history:
        if (
            run.analyzer_id in current
            or run.text_revision_id != text_revision_id
            or run.structure_revision_id != structure_revision_id
            or run.status not in {"succeeded", "partial"}
        ):
            continue
        definition = ANALYZERS_BY_ID.get(run.analyzer_id)
        if definition is None:
            continue
        if run.analyzer_version != definition.version:
            return True
        if run.config_json != _canonical_json(config_for_analyzer(run.analyzer_id)):
            return True
        state = state_for_analyzer(
            orchestrator,
            run.analyzer_id,
            document_id,
            structure_revision_id,
            current,
        )
        if run.state_fingerprint != (
            None if state is None else fingerprint_json(state)
        ):
            return True
        expected_policy = (
            fingerprint_json(
                cast(
                    JsonValue,
                    orchestrator.policy.input_values(definition.policy_inputs),
                )
            )
            if definition.policy_inputs
            else None
        )
        if run.policy_input_fingerprint != expected_policy:
            return True
        expected_prompt_id = PROMPT_IDS.get(run.analyzer_id)
        expected_prompt_version = (
            None
            if expected_prompt_id is None
            else get_prompt(expected_prompt_id).version
        )
        if (
            run.prompt_id != expected_prompt_id
            or run.prompt_version != expected_prompt_version
        ):
            return True
        linked_dependencies = dict(run.dependency_runs)
        for dependency in definition.dependencies:
            selected_dependency = current.get(dependency.analyzer_id)
            if selected_dependency is None:
                if dependency.analyzer_id in linked_dependencies:
                    return True
            elif linked_dependencies.get(dependency.analyzer_id) != (
                selected_dependency.id
            ):
                return True
    return False
