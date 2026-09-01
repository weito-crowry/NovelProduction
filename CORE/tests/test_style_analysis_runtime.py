from types import MappingProxyType

from novel_core.style_analysis.runtime_models import AnalysisPolicy
from novel_core.style_analysis.runtime_registry import (
    ANALYZERS,
    ANALYZERS_BY_ID,
)

ANALYZER_IDS = (
    "scene-boundary-detector",
    "entity-mention-extractor",
    "entity-resolver",
    "speaker-attribution",
    "term-candidate-extractor",
    "term-resolver",
    "term-explanation-detector",
    "scene-semantic-classifier",
    "block-semantic-classifier",
    "pov-classifier",
    "style-metrics-basic",
    "style-metrics-semantic",
)


def test_initial_registry_has_exact_analyzers() -> None:
    assert tuple(analyzer.id for analyzer in ANALYZERS) == ANALYZER_IDS
    assert tuple(ANALYZERS_BY_ID) == ANALYZER_IDS
    assert isinstance(ANALYZERS_BY_ID, MappingProxyType)
    assert all(analyzer.version == 1 for analyzer in ANALYZERS)
    assert all(
        analyzer.deterministic is None and analyzer.input_scope is None
        for analyzer in ANALYZERS
    )


def test_initial_registry_preserves_dependency_and_input_contracts() -> None:
    entity_resolver = ANALYZERS_BY_ID["entity-resolver"]
    assert entity_resolver.cacheable is False
    assert tuple(
        (dependency.analyzer_id, dependency.mode)
        for dependency in entity_resolver.dependencies
    ) == (("entity-mention-extractor", "subject_partial_allowed"),)
    assert entity_resolver.state_inputs == ("entity_registry_state",)
    assert entity_resolver.policy_inputs == ("entity_resolution_auto_merge",)

    speaker = ANALYZERS_BY_ID["speaker-attribution"]
    assert tuple(
        (dependency.analyzer_id, dependency.mode) for dependency in speaker.dependencies
    ) == (("entity-resolver", "subject_partial_allowed"),)
    assert speaker.state_inputs == ("mention_resolution",)
    assert speaker.policy_inputs == ()

    metrics = ANALYZERS_BY_ID["style-metrics-semantic"]
    assert tuple(
        (dependency.analyzer_id, dependency.mode) for dependency in metrics.dependencies
    ) == (
        ("speaker-attribution", "subject_partial_allowed"),
        ("term-resolver", "subject_partial_allowed"),
        ("term-explanation-detector", "subject_partial_allowed"),
        ("block-semantic-classifier", "subject_partial_allowed"),
    )
    assert metrics.state_inputs == (
        "metric_effective_state",
        "term_first_appearance",
    )
    assert metrics.policy_inputs == (
        "speaker_effective",
        "term_explanation_effective",
        "block_semantic_effective",
    )


def test_analysis_policy_has_only_specified_defaults() -> None:
    policy = AnalysisPolicy()
    assert policy.version == 1
    assert policy.entity_resolution_auto_merge == 0.90
    assert policy.term_resolution_auto_merge == 0.90
    assert policy.speaker_effective == 0.85
    assert policy.term_explanation_effective == 0.85
    assert policy.scene_label_effective == 0.80
    assert policy.block_semantic_effective == 0.75
    assert policy.pov_effective == 0.80
    assert policy.scene_boundary_auto_apply == 0.85
    assert policy.scene_boundary_candidate_min == 0.60
