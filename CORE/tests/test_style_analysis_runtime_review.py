import sqlite3

import pytest
from test_style_analysis_runtime import insert_run

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.analysis_runtime import (
    AnalysisRuntime,
    execution_fingerprint,
)
from novel_core.style_analysis.runtime_models import (
    AnalyzerDefinition,
    DependencyRunExpectation,
)
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID

pytest_plugins = ("test_style_analysis_runtime",)


@pytest.mark.parametrize(
    "stale_kwargs",
    [
        {"config_json": '{"stale":true}'},
        {"state_fingerprint": "s" * 64},
        {"policy_input_fingerprint": "p" * 64},
        {"prompt_id": "scene-v1", "prompt_version": 2},
    ],
)
def test_dependency_current_filters_all_current_inputs_before_newest(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
    stale_kwargs: dict[str, object],
) -> None:
    _, repository, runtime, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    current_dependency_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-mention-extractor",
    )
    stale_dependency_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-mention-extractor",
        **stale_kwargs,
    )
    parent_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-resolver",
        dependency_runs=(("entity-mention-extractor", current_dependency_id),),
    )
    parent = repository.get_run(parent_id)
    assert parent is not None

    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="entity-resolver",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint=None,
            policy_input_fingerprint=None,
            dependency_runs=(("entity-mention-extractor", current_dependency_id),),
            dependency_expectations=(
                DependencyRunExpectation(
                    analyzer_id="entity-mention-extractor",
                    run_id=current_dependency_id,
                    config_json='{"a":1,"b":2}',
                ),
            ),
        )
        == parent
    )
    assert stale_dependency_id != current_dependency_id


def test_subject_partial_dependency_prefers_current_succeeded_over_partial(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    _, repository, runtime, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    partial_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-resolver",
        status="partial",
    )
    succeeded_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-resolver",
        status="succeeded",
    )
    parent_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="speaker-attribution",
        dependency_runs=(("entity-resolver", succeeded_id),),
    )
    parent = repository.get_run(parent_id)
    assert parent is not None

    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="speaker-attribution",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint=None,
            policy_input_fingerprint=None,
            dependency_runs=(("entity-resolver", succeeded_id),),
            dependency_expectations=(
                DependencyRunExpectation(
                    analyzer_id="entity-resolver",
                    run_id=succeeded_id,
                    config_json='{"a":1,"b":2}',
                ),
            ),
        )
        == parent
    )
    assert partial_id != succeeded_id


def test_top_level_current_run_requires_registry_analyzer_version(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    _, repository, _, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    analyzer = AnalyzerDefinition(
        id="versioned-test",
        version=2,
        deterministic=None,
        cacheable=True,
        dependencies=(),
        state_inputs=(),
        policy_inputs=(),
        input_scope=None,
    )
    versioned_runtime = AnalysisRuntime(
        repository,
        analyzers={**ANALYZERS_BY_ID, "versioned-test": analyzer},
    )
    version_one_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="versioned-test",
        analyzer_version=1,
    )
    assert (
        versioned_runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="versioned-test",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint=None,
            policy_input_fingerprint=None,
            dependency_runs=(),
        )
        is None
    )

    version_two_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="versioned-test",
        analyzer_version=2,
    )
    assert versioned_runtime.resolve_current_run(
        document_id=document_id,
        analyzer_id="versioned-test",
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_version=2,
        config_json='{"a":1,"b":2}',
        state_fingerprint=None,
        policy_input_fingerprint=None,
        dependency_runs=(),
    ) == repository.get_run(version_two_id)
    assert version_one_id != version_two_id


def test_top_level_cache_hit_requires_registry_analyzer_version(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    _, repository, _, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    analyzer = AnalyzerDefinition(
        id="versioned-cache-test",
        version=2,
        deterministic=None,
        cacheable=True,
        dependencies=(),
        state_inputs=(),
        policy_inputs=(),
        input_scope=None,
    )
    versioned_runtime = AnalysisRuntime(
        repository,
        analyzers={**ANALYZERS_BY_ID, "versioned-cache-test": analyzer},
    )
    config_json = '{"a":1,"b":2}'
    fingerprint = execution_fingerprint(
        analyzer_id="versioned-cache-test",
        analyzer_version=2,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        config=config_json,
        state_fingerprint=None,
        policy_input_fingerprint=None,
        dependency_runs=(),
        model_provider=None,
        model_id=None,
    )
    version_one_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="versioned-cache-test",
        analyzer_version=1,
    )
    version_two_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="versioned-cache-test",
        analyzer_version=2,
        config_json=config_json,
        fingerprint=fingerprint,
    )

    common = dict(
        document_id=document_id,
        analyzer_id="versioned-cache-test",
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        config_json=config_json,
        state_fingerprint=None,
        policy_input_fingerprint=None,
        dependency_runs=(),
        model_provider=None,
        model_id=None,
    )
    assert versioned_runtime.resolve_cache_hit(analyzer_version=1, **common) is None
    assert versioned_runtime.resolve_cache_hit(
        analyzer_version=2, **common
    ) == repository.get_run(version_two_id)
    assert version_one_id != version_two_id
