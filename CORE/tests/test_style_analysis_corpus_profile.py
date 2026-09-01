from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.style_analysis.aggregate_service import AggregateService
from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.corpus_models import AggregateSpec
from novel_core.style_analysis.corpus_repository import CorpusRepository
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.profile_service import ProfileService
from novel_core.style_analysis.semantic_repository import SemanticRepository
from novel_core.style_analysis.source_models import SourceEpisodeInput, SourceWorkInput
from novel_core.style_analysis.source_repository import StyleSourceRepository

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations"


def open_test_database(tmp_path: Path) -> sqlite3.Connection:
    return open_database(
        DatabaseConfig(db_path=tmp_path / "story.db", migration_dir=MIGRATION_DIR)
    )


def import_work(
    connection: sqlite3.Connection, *, title: str = "Reference", count: int = 2
) -> int:
    episodes = tuple(
        SourceEpisodeInput(
            external_episode_id=str(index),
            title=f"Episode {index}",
            order_index=index,
            raw_text=f"本文{index}。",
            metadata={"scene_break_offsets_raw": []},
        )
        for index in range(1, count + 1)
    )
    payload = title.encode() + str(count).encode()
    result = StyleSourceRepository(connection).insert_import(
        source_type="text",
        external_work_id=hashlib.sha256(payload).hexdigest(),
        original_filename=f"{title}.txt",
        adapter_id="style-source-text",
        adapter_version=1,
        payload=payload,
        media_type="text/plain",
        source_metadata={},
        work=SourceWorkInput(
            title=title,
            author_name=None,
            metadata={},
            episodes=episodes,
        ),
    )
    for episode in StyleSourceRepository(connection).list_reference_episodes(
        result.work.id
    ):
        assert episode.style_document_id is not None
        assert episode.current_text_revision_id is not None
        DocumentAnalysisOrchestrator(connection, model_client=None).analyze_document(
            document_id=episode.style_document_id,
            text_revision_id=episode.current_text_revision_id,
            preset="deterministic",
        )
    connection.commit()
    return result.work.id


def test_measurements_are_persisted_for_current_basic_run(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path)
    try:
        work_id = import_work(connection, count=1)
        row = connection.execute(
            "SELECT sar.id FROM style_analysis_runs sar "
            "JOIN style_documents sd ON sd.id = sar.document_id "
            "JOIN style_reference_episodes re ON re.id = sd.reference_episode_id "
            "WHERE re.reference_work_id = ? "
            "AND sar.analyzer_id = 'style-metrics-basic'",
            (work_id,),
        ).fetchone()
        assert row is not None
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_measurements WHERE analysis_run_id = ?", row
            ).fetchone()[0]
            > 0
        )
    finally:
        connection.close()


def test_term_prefix_uses_in_flight_target_lineage_before_pointer_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = open_test_database(tmp_path)
    try:
        work_id = import_work(connection, count=2)
        episodes = StyleSourceRepository(connection).list_reference_episodes(work_id)
        target = episodes[1]
        assert target.style_document_id is not None
        assert target.current_text_revision_id is not None
        assert target.current_structure_revision_id is not None
        digest = "d" * 64
        cursor = connection.execute(
            "INSERT INTO style_structure_revisions "
            "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
            "source_kind, fingerprint) VALUES (?, 2, 'test', 1, 'automatic', ?)",
            (target.current_text_revision_id, digest),
        )
        assert cursor.lastrowid is not None
        in_flight_structure_id = int(cursor.lastrowid)
        runs = AnalysisRunRepository(connection)
        assert episodes[0].style_document_id is not None
        assert episodes[0].current_text_revision_id is not None
        assert episodes[0].current_structure_revision_id is not None
        prior_run_id = runs.insert_run(
            document_id=episodes[0].style_document_id,
            analyzer_id="term-resolver",
            analyzer_version=1,
            text_revision_id=episodes[0].current_text_revision_id,
            structure_revision_id=episodes[0].current_structure_revision_id,
            status="succeeded",
            fingerprint=digest,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        run_id = runs.insert_run(
            document_id=target.style_document_id,
            analyzer_id="term-resolver",
            analyzer_version=1,
            text_revision_id=target.current_text_revision_id,
            structure_revision_id=in_flight_structure_id,
            status="succeeded",
            fingerprint=digest,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        resolver = CurrentRunResolver(connection)
        prior_run = runs.get_run(prior_run_id)
        assert prior_run is not None
        monkeypatch.setattr(resolver, "resolve", lambda *_args: prior_run)
        entries, complete = resolver.term_prefix(
            target.style_document_id,
            target.current_text_revision_id,
            in_flight_structure_id,
            run_id,
        )
        assert complete
        assert entries[-1].document_id == target.style_document_id
        assert entries[-1].text_revision_id == target.current_text_revision_id
        assert entries[-1].structure_revision_id == in_flight_structure_id
        assert entries[-1].resolver_status == "succeeded"
    finally:
        connection.close()


def test_metric_state_uses_reference_term_scope_without_registry_novelty(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        work_id = import_work(connection, count=2)
        episode = StyleSourceRepository(connection).list_reference_episodes(work_id)[0]
        assert episode.style_document_id is not None
        assert episode.current_structure_revision_id is not None
        term_cursor = connection.execute(
            "INSERT INTO style_terms "
            "(reference_work_id, canonical_label, term_type, origin) "
            "VALUES (?, '固有語', 'other', 'manual')",
            (work_id,),
        )
        assert term_cursor.lastrowid is not None
        term_id = int(term_cursor.lastrowid)
        run_id = connection.execute(
            "SELECT id FROM style_analysis_runs WHERE document_id = ? "
            "ORDER BY id LIMIT 1",
            (episode.style_document_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO style_inference_reviews "
            "(reference_work_id, subject_type, subject_id, field_path, "
            "analysis_run_id, review_status) VALUES (?, 'term', ?, "
            "'term.novelty', ?, 'confirmed')",
            (work_id, term_id, run_id),
        )
        connection.commit()

        resolver = CurrentRunResolver(connection)
        metric_state = resolver.state._metric_effective_state(
            episode.style_document_id, episode.current_structure_revision_id
        )
        assert any(
            item["kind"] == "review"
            and item["subject_type"] == "term"
            and item["subject_id"] == term_id
            and item["field_path"] == "term.novelty"
            for item in metric_state
        )
        connection.execute(
            "INSERT INTO style_manual_overrides "
            "(reference_work_id, subject_type, subject_id, field_path, operation, "
            "value_json, structure_revision_id) VALUES (?, 'mention', 999, "
            "'mention.entity_id', 'set', '{\"value\":1}', ?)",
            (work_id, episode.current_structure_revision_id),
        )
        connection.commit()
        metric_state = resolver.state._metric_effective_state(
            episode.style_document_id, episode.current_structure_revision_id
        )
        assert not any(
            item["field_path"] == "mention.entity_id" for item in metric_state
        )
        assert resolver.state._mention_resolution_state(
            episode.style_document_id,
            episode.current_structure_revision_id,
            run_id,
        ) == [
            {
                "mention_id": 999,
                "manual_override": {
                    "field_path": "mention.entity_id",
                    "operation": "set",
                    "value_json": '{"value":1}',
                },
            }
        ]
        registry_state = resolver.state._term_registry_state(episode.style_document_id)
        connection.execute(
            "INSERT INTO style_manual_overrides "
            "(reference_work_id, subject_type, subject_id, field_path, operation, "
            "value_json, structure_revision_id) VALUES (?, 'term', ?, "
            "'term.novelty', 'set', '{\"value\":\"work_specific\"}', ?)",
            (work_id, term_id, episode.current_structure_revision_id),
        )
        connection.commit()
        metric_state = resolver.state._metric_effective_state(
            episode.style_document_id, episode.current_structure_revision_id
        )
        assert any(
            item["kind"] == "override"
            and item["subject_id"] == term_id
            and item["field_path"] == "term.novelty"
            for item in metric_state
        )
        assert (
            resolver.state._term_registry_state(episode.style_document_id)
            == registry_state
        )
    finally:
        connection.close()


def test_corpus_membership_and_document_aggregate_use_current_rows(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        work_id = import_work(connection, count=2)
        corpora = CorpusRepository(connection)
        corpus = corpora.create("Corpus")
        membership = corpora.add_work(corpus.id, work_id, include_all_episodes=True)
        episodes = StyleSourceRepository(connection).list_reference_episodes(work_id)
        corpora.set_episode(corpus.id, episodes[0].id, "exclude")
        assert corpora.list_effective_episode_ids(corpus.id) == (episodes[1].id,)
        connection.commit()

        result = AggregateService(connection).recompute(
            (
                AggregateSpec(
                    "corpus", corpus.id, "document", "{}", "text.char_count", 1
                ),
            )
        )
        assert len(result.aggregates) == 9
        median = next(item for item in result.aggregates if item.statistic == "median")
        assert isinstance(median.value_real, float)
        assert median.source_measurement_count == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM style_aggregate_measurements WHERE aggregate_id = ?",
            (median.id,),
        ).fetchone() == (1,)
        assert membership.id > 0
    finally:
        connection.close()


def test_aggregate_source_change_marks_historical_rows_stale(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path)
    try:
        first_work = import_work(connection, title="First", count=1)
        corpora = CorpusRepository(connection)
        corpus = corpora.create("Corpus")
        corpora.add_work(corpus.id, first_work, include_all_episodes=True)
        service = AggregateService(connection)
        service.recompute(
            (
                AggregateSpec(
                    "corpus", corpus.id, "document", "{}", "text.char_count", 1
                ),
            )
        )
        second_work = import_work(connection, title="Second", count=1)
        corpora.add_work(corpus.id, second_work, include_all_episodes=True)
        connection.commit()
        historical = service.list_with_staleness(
            container_type="corpus", container_id=corpus.id
        )
        assert historical
        assert all(item.stale for item in historical)
    finally:
        connection.close()


def test_scene_filter_unknown_is_skipped_but_unclear_is_a_normal_value(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        work_id = import_work(connection, count=1)
        corpora = CorpusRepository(connection)
        corpus = corpora.create("Corpus")
        corpora.add_work(corpus.id, work_id, include_all_episodes=True)
        connection.commit()
        service = AggregateService(connection)
        unknown = service.recompute(
            (
                AggregateSpec(
                    "corpus",
                    corpus.id,
                    "scene",
                    '{"scene":{"function":["daily"]}}',
                    "text.char_count",
                    1,
                ),
            )
        )
        assert unknown.aggregates == ()
        assert "SCENE_SELECTOR_UNAVAILABLE:function" in unknown.warnings

        episode = StyleSourceRepository(connection).list_reference_episodes(work_id)[0]
        assert episode.style_document_id is not None
        assert episode.current_text_revision_id is not None
        assert episode.current_structure_revision_id is not None
        scene_id = connection.execute(
            "SELECT id FROM style_scenes WHERE structure_revision_id = ?",
            (episode.current_structure_revision_id,),
        ).fetchone()[0]
        prompt = get_prompt("style.scene_semantics")
        runs = AnalysisRunRepository(connection)
        run_id = runs.insert_run(
            document_id=episode.style_document_id,
            analyzer_id="scene-semantic-classifier",
            analyzer_version=1,
            text_revision_id=episode.current_text_revision_id,
            structure_revision_id=episode.current_structure_revision_id,
            status="running",
            fingerprint="a" * 64,
            config_json='{"scene_taxonomy_version":1}',
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            started_at="2026-09-01T00:00:00+00:00",
        )
        SemanticRepository(connection).insert_annotation(
            annotation_type="scene.function",
            subject_type="scene",
            subject_id=scene_id,
            value_json='{"labels":[{"confidence":1.0,"label":"unclear"}]}',
            confidence=1.0,
            analysis_run_id=run_id,
        )
        runs.finish_run(run_id, status="succeeded")
        connection.commit()
        unclear = service.recompute(
            (
                AggregateSpec(
                    "corpus",
                    corpus.id,
                    "scene",
                    '{"scene":{"function":["unclear"]}}',
                    "text.char_count",
                    1,
                ),
            )
        )
        assert len(unclear.aggregates) == 9
        assert all(item.skipped_target_count == 0 for item in unclear.aggregates)
        assert all(item.filter_state_fingerprint for item in unclear.aggregates)
    finally:
        connection.close()


def test_manual_profile_accepts_fractional_count_rule_range(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path)
    try:
        result = ProfileService(connection).create_manual(
            name="Manual",
            rules=(
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "dialogue.utterance_count",
                    "metric_version": 1,
                    "min_value": 0.5,
                    "max_value": 1.5,
                    "preferred_value": 1.0,
                    "weight": 1.0,
                    "enabled": True,
                    "severity_policy": "standard",
                },
            ),
        )
        assert result.version.version_no == 1
        assert result.rules[0].source_kind == "manual"
        assert result.rules[0].min_value == 0.5
        assert result.warnings == ()
    finally:
        connection.close()


def test_corpus_profile_uses_exact_three_aggregate_ids_and_new_version_is_manual(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        work_id = import_work(connection, count=5)
        corpora = CorpusRepository(connection)
        corpus = corpora.create("Corpus")
        corpora.add_work(corpus.id, work_id, include_all_episodes=True)
        connection.commit()
        aggregate_result = AggregateService(connection).recompute(
            (
                AggregateSpec(
                    "corpus", corpus.id, "document", "{}", "text.char_count", 1
                ),
            )
        )
        by_statistic = {item.statistic: item.id for item in aggregate_result.aggregates}
        service = ProfileService(connection)
        created = service.create_from_corpus(
            corpus_id=corpus.id,
            name="Reference style",
            aggregate_groups=(
                {
                    "preferred_aggregate_id": by_statistic["median"],
                    "min_aggregate_id": by_statistic["p25"],
                    "max_aggregate_id": by_statistic["p75"],
                },
            ),
        )
        assert created.rules[0].source_kind == "corpus"
        assert set(service.aggregate_sources(created.rules[0].id)) == {
            (by_statistic["median"], "preferred"),
            (by_statistic["p25"], "min"),
            (by_statistic["p75"], "max"),
        }
        new_version = service.create_version(
            created.profile.id,
            parent_version_no=1,
            rules=(
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "text.char_count",
                    "metric_version": 1,
                    "min_value": 1.5,
                    "max_value": 8.5,
                },
            ),
        )
        assert new_version.version.version_no == 2
        assert new_version.rules[0].source_kind == "manual"
        assert service.aggregate_sources(new_version.rules[0].id) == ()
        assert service.get_profile(created.profile.id).active_version_id is None
        service.activate(created.profile.id, 2)
        assert (
            service.get_profile(created.profile.id).active_version_id
            == new_version.version.id
        )
        service.archive(created.profile.id)
        assert service.get_profile(created.profile.id).status == "archived"
    finally:
        connection.close()


def test_profile_rejects_boolean_rule_number_and_requires_parent_version(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        with pytest.raises(ValueError, match="PROFILE_RULE_NUMBER_INVALID"):
            ProfileService(connection).create_manual(
                name="Invalid",
                rules=(
                    {
                        "target_scope": "document",
                        "scope_selector": {},
                        "metric_name": "text.char_count",
                        "metric_version": 1,
                        "min_value": True,
                        "max_value": 2,
                    },
                ),
            )
        profile = ProfileService(connection).create_manual(name="Valid", rules=())
        with pytest.raises(ValueError, match="PROFILE_PARENT_VERSION_NOT_FOUND"):
            ProfileService(connection).create_version(
                profile.profile.id, parent_version_no=2, rules=()
            )
    finally:
        connection.close()


def test_aggregate_rejects_stale_metric_version_and_invalid_filter(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        service = AggregateService(connection)
        with pytest.raises(ValueError, match="METRIC_NOT_FOUND"):
            service.recompute(
                (
                    AggregateSpec(
                        "reference_work", 1, "document", "{}", "text.char_count", 2
                    ),
                )
            )
        with pytest.raises(ValueError, match="AGGREGATE_FILTER_INVALID"):
            service.recompute(
                (
                    AggregateSpec(
                        "reference_work",
                        1,
                        "scene",
                        '{"extra":{}}',
                        "text.char_count",
                        1,
                    ),
                )
            )
        with pytest.raises(ValueError, match="AGGREGATE_FILTER_INVALID"):
            service.recompute(
                (
                    AggregateSpec(
                        "reference_work",
                        1,
                        "scene",
                        '{"scene":{"function":["not-a-taxonomy-label"]}}',
                        "text.char_count",
                        1,
                    ),
                )
            )
    finally:
        connection.close()


def test_disabled_duplicate_profile_rules_do_not_block_enabled_rule(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        result = ProfileService(connection).create_manual(
            name="Manual",
            rules=(
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "text.char_count",
                    "metric_version": 1,
                    "enabled": False,
                },
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "text.char_count",
                    "metric_version": 1,
                    "enabled": True,
                    "min_value": 1,
                    "max_value": 2,
                },
            ),
        )
        assert len(result.rules) == 2
    finally:
        connection.close()
