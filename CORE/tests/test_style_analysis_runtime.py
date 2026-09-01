import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import MappingProxyType

import pytest
from test_style_analysis_migration import open_test_database

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.analysis_runtime import (
    AnalysisRuntime,
    execution_fingerprint,
)
from novel_core.style_analysis.runtime_models import (
    AnalysisPolicy,
    AnalyzerDefinition,
    DependencyRunExpectation,
    DependencySpec,
)
from novel_core.style_analysis.runtime_registry import ANALYZERS, ANALYZERS_BY_ID

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


@pytest.fixture
def runtime_context(
    tmp_path: Path,
) -> Iterator[
    tuple[sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int]
]:
    connection = open_test_database(tmp_path / "story.db")
    connection.execute(
        "INSERT INTO works (slug, working_title) VALUES ('runtime', 'Runtime')"
    )
    work_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'Chapter')",
        (work_id,),
    )
    chapter_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.execute(
        "INSERT INTO episodes (work_id, chapter_id, position, title) "
        "VALUES (?, ?, 1, 'Episode')",
        (work_id, chapter_id),
    )
    episode_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.execute(
        "INSERT INTO style_documents "
        "(kind, project_work_id, project_episode_id) VALUES (?, ?, ?)",
        ("project_episode_draft", work_id, episode_id),
    )
    document_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    digest = "a" * 64
    connection.execute(
        "INSERT INTO style_text_revisions "
        "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
        "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
        "normalizer_id, normalizer_version) "
        "VALUES (?, 1, 1, 'raw', 'canonical', ?, ?, ?, 'test', 1)",
        (document_id, digest, digest, digest),
    )
    text_revision_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.execute(
        "INSERT INTO style_structure_revisions "
        "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
        "source_kind, fingerprint) VALUES (?, 1, 'test', 1, 'automatic', ?)",
        (text_revision_id, digest),
    )
    structure_revision_row = connection.execute("SELECT last_insert_rowid()").fetchone()
    assert structure_revision_row is not None
    structure_revision_id = structure_revision_row[0]
    connection.commit()
    repository = AnalysisRunRepository(connection)
    runtime = AnalysisRuntime(repository)
    try:
        yield (
            connection,
            repository,
            runtime,
            document_id,
            text_revision_id,
            structure_revision_id,
        )
    finally:
        connection.close()


def insert_run(
    repository: AnalysisRunRepository,
    *,
    document_id: int,
    text_revision_id: int,
    structure_revision_id: int,
    analyzer_id: str,
    status: str = "succeeded",
    state_fingerprint: str | None = None,
    policy_input_fingerprint: str | None = None,
    registry_input_fingerprint: str | None = None,
    dependency_runs: tuple[tuple[str, int], ...] = (),
    config_json: str = '{"b":2,"a":1}',
    analyzer_version: int = 1,
    fingerprint: str = "b" * 64,
    prompt_id: str | None = None,
    prompt_version: int | None = None,
) -> int:
    run_id = repository.insert_run(
        document_id=document_id,
        analyzer_id=analyzer_id,
        analyzer_version=analyzer_version,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        status=status,
        fingerprint=fingerprint,
        config_json=config_json,
        state_fingerprint=state_fingerprint,
        policy_input_fingerprint=policy_input_fingerprint,
        registry_input_fingerprint=registry_input_fingerprint,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        started_at="2026-01-01T00:00:00Z",
    )
    for _dependency_analyzer_id, dependency_run_id in dependency_runs:
        repository.add_dependency(run_id, dependency_run_id)
    repository.commit()
    return run_id


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


def test_execution_fingerprint_ignores_json_object_key_order() -> None:
    first = execution_fingerprint(
        analyzer_id="style-metrics-basic",
        analyzer_version=1,
        text_revision_id=1,
        structure_revision_id=2,
        config={"b": 2, "a": 1},
        state_fingerprint=None,
        policy_input_fingerprint=None,
        dependency_runs=(),
        model_provider=None,
        model_id=None,
    )
    second = execution_fingerprint(
        analyzer_id="style-metrics-basic",
        analyzer_version=1,
        text_revision_id=1,
        structure_revision_id=2,
        config={"a": 1, "b": 2},
        state_fingerprint=None,
        policy_input_fingerprint=None,
        dependency_runs=(),
        model_provider=None,
        model_id=None,
    )
    assert first == second
    assert len(first) == 64
    assert first == first.lower()


def test_current_run_matches_relevant_inputs_and_ignores_registry_provenance(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    (
        connection,
        repository,
        runtime,
        document_id,
        text_revision_id,
        structure_revision_id,
    ) = runtime_context
    run_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="style-metrics-basic",
        state_fingerprint="c" * 64,
        policy_input_fingerprint="d" * 64,
        registry_input_fingerprint="e" * 64,
    )
    run = repository.get_run(run_id)
    assert run is not None
    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="style-metrics-basic",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint="c" * 64,
            policy_input_fingerprint="d" * 64,
            dependency_runs=(),
        )
        == run
    )
    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="style-metrics-basic",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint="c" * 64,
            policy_input_fingerprint="0" * 64,
            dependency_runs=(),
        )
        is None
    )
    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="style-metrics-basic",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint="c" * 64,
            policy_input_fingerprint="d" * 64,
            dependency_runs=(),
        )
        == run
    )
    assert connection.execute(
        "SELECT registry_input_fingerprint FROM style_analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone() == ("e" * 64,)
    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="style-metrics-basic",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint="c" * 64,
            policy_input_fingerprint="d" * 64,
            dependency_runs=(),
        )
        == run
    )


def test_non_cacheable_resolver_current_run_is_resolvable(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    _, repository, runtime, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    dependency_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-mention-extractor",
    )
    resolver_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-resolver",
        state_fingerprint="c" * 64,
        policy_input_fingerprint="d" * 64,
        dependency_runs=(("entity-mention-extractor", dependency_id),),
    )
    resolver = repository.get_run(resolver_id)
    assert resolver is not None
    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="entity-resolver",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint="c" * 64,
            policy_input_fingerprint="d" * 64,
            dependency_runs=(("entity-mention-extractor", dependency_id),),
            dependency_expectations=(
                DependencyRunExpectation(
                    analyzer_id="entity-mention-extractor",
                    run_id=dependency_id,
                    config_json='{"a":1,"b":2}',
                ),
            ),
        )
        == resolver
    )


def test_non_cacheable_resolver_is_not_a_cache_hit(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    _, repository, runtime, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    dependency_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-mention-extractor",
    )
    fingerprint = execution_fingerprint(
        analyzer_id="entity-resolver",
        analyzer_version=1,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        config='{"a":1,"b":2}',
        state_fingerprint="c" * 64,
        policy_input_fingerprint="d" * 64,
        dependency_runs=(("entity-mention-extractor", dependency_id),),
        model_provider=None,
        model_id=None,
    )
    run_id = repository.insert_run(
        document_id=document_id,
        analyzer_id="entity-resolver",
        analyzer_version=1,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        status="succeeded",
        fingerprint=fingerprint,
        config_json='{"a":1,"b":2}',
        state_fingerprint="c" * 64,
        policy_input_fingerprint="d" * 64,
        started_at="2026-01-01T00:00:00Z",
    )
    repository.add_dependency(run_id, dependency_id)
    repository.commit()

    assert (
        runtime.resolve_cache_hit(
            document_id=document_id,
            analyzer_id="entity-resolver",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint="c" * 64,
            policy_input_fingerprint="d" * 64,
            dependency_runs=(("entity-mention-extractor", dependency_id),),
            model_provider=None,
            model_id=None,
        )
        is None
    )


def test_current_run_requires_current_dependency_inputs(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    _, repository, runtime, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    stale_dependency_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-mention-extractor",
        config_json='{"stale":true}',
    )
    current_dependency_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-mention-extractor",
    )
    resolver_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-resolver",
        state_fingerprint="c" * 64,
        policy_input_fingerprint="d" * 64,
        dependency_runs=(("entity-mention-extractor", stale_dependency_id),),
    )
    assert repository.get_run(resolver_id) is not None

    assert (
        runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="entity-resolver",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint="c" * 64,
            policy_input_fingerprint="d" * 64,
            dependency_runs=(("entity-mention-extractor", stale_dependency_id),),
            dependency_expectations=(
                DependencyRunExpectation(
                    analyzer_id="entity-mention-extractor",
                    run_id=stale_dependency_id,
                    config_json='{"a":1,"b":2}',
                ),
            ),
        )
        is None
    )
    assert current_dependency_id != stale_dependency_id


def test_current_run_checks_prompt_identity_and_version_and_null_contract(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    _, repository, runtime, document_id, text_revision_id, structure_revision_id = (
        runtime_context
    )
    prompt_analyzer = AnalyzerDefinition(
        id="prompt-test",
        version=1,
        deterministic=None,
        cacheable=True,
        dependencies=(),
        state_inputs=(),
        policy_inputs=(),
        input_scope=None,
    )
    prompt_runtime = AnalysisRuntime(
        repository,
        analyzers={**ANALYZERS_BY_ID, "prompt-test": prompt_analyzer},
    )
    prompt_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="prompt-test",
        prompt_id="scene-v1",
        prompt_version=1,
    )
    assert prompt_runtime.resolve_current_run(
        document_id=document_id,
        analyzer_id="prompt-test",
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_version=1,
        config_json='{"a":1,"b":2}',
        state_fingerprint=None,
        policy_input_fingerprint=None,
        dependency_runs=(),
        prompt_id="scene-v1",
        prompt_version=1,
    ) == repository.get_run(prompt_id)
    assert (
        prompt_runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="prompt-test",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint=None,
            policy_input_fingerprint=None,
            dependency_runs=(),
            prompt_id="scene-v1",
            prompt_version=2,
        )
        is None
    )

    null_prompt_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="style-metrics-basic",
    )
    assert runtime.resolve_current_run(
        document_id=document_id,
        analyzer_id="style-metrics-basic",
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_version=1,
        config_json='{"a":1,"b":2}',
        state_fingerprint=None,
        policy_input_fingerprint=None,
        dependency_runs=(),
        prompt_id=None,
        prompt_version=None,
    ) == repository.get_run(null_prompt_id)


def test_analysis_run_repository_persists_provenance_and_links(
    runtime_context: tuple[
        sqlite3.Connection, AnalysisRunRepository, AnalysisRuntime, int, int, int
    ],
) -> None:
    (
        _,
        repository,
        _,
        document_id,
        text_revision_id,
        structure_revision_id,
    ) = runtime_context
    dependency_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="entity-mention-extractor",
    )
    run_id = repository.insert_run(
        document_id=document_id,
        analyzer_id="speaker-attribution",
        analyzer_version=1,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        status="partial",
        fingerprint="f" * 64,
        config_json='{"config":true}',
        analysis_policy_version=4,
        policy_input_fingerprint="1" * 64,
        state_fingerprint="2" * 64,
        registry_input_fingerprint="3" * 64,
        model_provider="openai_compatible",
        model_id="test-model",
        prompt_id="speaker-v1",
        prompt_version=2,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        error_code="PARTIAL_SUBJECT",
        error_message="one subject failed",
        warning_json='[{"code":"subject_failed"}]',
    )
    repository.add_dependency(run_id, dependency_id)
    repository.add_structure_analysis_source(structure_revision_id, run_id)
    repository.add_structure_analysis_source(structure_revision_id, dependency_id)
    repository.commit()

    record = repository.get_run(run_id)
    assert record is not None
    assert record.status == "partial"
    assert record.analysis_policy_version == 4
    assert record.policy_input_fingerprint == "1" * 64
    assert record.state_fingerprint == "2" * 64
    assert record.registry_input_fingerprint == "3" * 64
    assert record.model_provider == "openai_compatible"
    assert record.model_id == "test-model"
    assert record.prompt_id == "speaker-v1"
    assert record.prompt_version == 2
    assert record.finished_at == "2026-01-01T00:00:01Z"
    assert record.error_code == "PARTIAL_SUBJECT"
    assert record.error_message == "one subject failed"
    assert record.warning_json == '[{"code":"subject_failed"}]'
    assert record.dependency_runs == (("entity-mention-extractor", dependency_id),)

    with pytest.raises(sqlite3.IntegrityError):
        repository.add_dependency(run_id, run_id)
    repository.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        repository.add_dependency(run_id, dependency_id)


def test_partial_dependency_is_allowed_only_for_partial_mode(
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
        state_fingerprint="c" * 64,
        policy_input_fingerprint="d" * 64,
    )
    speaker_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="speaker-attribution",
        dependency_runs=(("entity-resolver", partial_id),),
    )
    speaker = repository.get_run(speaker_id)
    assert speaker is not None
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
            dependency_runs=(("entity-resolver", partial_id),),
            dependency_expectations=(
                DependencyRunExpectation(
                    analyzer_id="entity-resolver",
                    run_id=partial_id,
                    config_json='{"a":1,"b":2}',
                    state_fingerprint="c" * 64,
                    policy_input_fingerprint="d" * 64,
                ),
            ),
        )
        == speaker
    )

    complete = AnalyzerDefinition(
        id="complete-test",
        version=1,
        deterministic=None,
        cacheable=True,
        dependencies=(DependencySpec("entity-resolver", "complete"),),
        state_inputs=(),
        policy_inputs=(),
        input_scope=None,
    )
    complete_runtime = AnalysisRuntime(
        repository,
        analyzers={**ANALYZERS_BY_ID, "complete-test": complete},
    )
    complete_id = insert_run(
        repository,
        document_id=document_id,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_revision_id,
        analyzer_id="complete-test",
        dependency_runs=(("entity-resolver", partial_id),),
    )
    assert (
        complete_runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id="complete-test",
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            analyzer_version=1,
            config_json='{"a":1,"b":2}',
            state_fingerprint=None,
            policy_input_fingerprint=None,
            dependency_runs=(("entity-resolver", partial_id),),
            dependency_expectations=(
                DependencyRunExpectation(
                    analyzer_id="entity-resolver",
                    run_id=partial_id,
                    config_json='{"a":1,"b":2}',
                    state_fingerprint="c" * 64,
                    policy_input_fingerprint="d" * 64,
                ),
            ),
        )
        is None
    )
    assert repository.get_run(complete_id) is not None
