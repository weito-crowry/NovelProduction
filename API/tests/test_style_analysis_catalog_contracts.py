from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.runtime_models import JobRecord
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID
from pydantic import ValidationError
from test_style_analysis_jobs import (
    _create_reference_analysis,
    _FailingSpeakerModel,
    insert_job_row,
)

from novel_api.project_registry import ProjectRegistry
from novel_api.routes.style_analysis import _job_response
from novel_api.schemas.style_analysis import ProfileRuleRequest
from novel_api.style_analysis import catalog_current as catalog_current_module
from novel_api.style_analysis.catalog_service import StyleAnalysisCatalogService
from novel_api.style_analysis.job_service import StyleJobService


def test_job_response_exposes_progress_dto() -> None:
    job = JobRecord(
        id=1,
        job_type="analyze_document",
        payload_json="{}",
        status="running",
        cancel_requested=0,
        progress_current=2,
        progress_total=5,
        result_json="{}",
        warning_json="[]",
        created_at="now",
        started_at="now",
        finished_at=None,
        error_code=None,
        error_message=None,
        version=1,
    )
    response = _job_response(job)
    assert response.progress == {"current": 2, "total": 5}


def test_profile_rule_api_rejects_boolean_numeric_values() -> None:
    with pytest.raises(ValidationError):
        ProfileRuleRequest.model_validate(
            {
                "target_scope": "document",
                "scope_selector": {},
                "metric_name": "text.char_count",
                "metric_version": 1,
                "min_value": True,
                "max_value": 2,
            }
        )


def test_profile_rule_api_requires_all_control_fields() -> None:
    with pytest.raises(ValidationError):
        ProfileRuleRequest.model_validate(
            {
                "target_scope": "document",
                "scope_selector": {},
                "metric_name": "text.char_count",
                "metric_version": 1,
                "min_value": 0,
                "max_value": 2,
            }
        )


def test_partial_terminal_status_is_limited_to_analysis_jobs(
    data_root: Path,
) -> None:
    ProjectRegistry(data_root).create("Demo", project_id="demo")
    service = StyleJobService(data_root=data_root)
    lint_id = insert_job_row(
        data_root / "demo" / "story.db",
        status="queued",
        job_type="run_lint",
    )

    with pytest.raises(ValueError, match="PARTIAL_STATUS_NOT_ALLOWED"):
        service.set_status("demo", lint_id, "partial")

    document_id = insert_job_row(
        data_root / "demo" / "story.db",
        status="queued",
        job_type="analyze_document",
    )
    assert service.set_status("demo", document_id, "partial").status == "partial"


def test_semantics_selects_current_partial_run_over_historical_success(
    data_root: Path,
) -> None:
    connection, document_id, text_revision_id, first = _create_reference_analysis(
        data_root
    )
    try:
        reference_work_id = connection.execute(
            "SELECT reference_work_id FROM style_reference_episodes "
            "WHERE id = (SELECT reference_episode_id FROM style_documents "
            "WHERE id = ?)",
            (document_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO style_entities "
            "(reference_work_id, entity_type, canonical_name, origin) "
            "VALUES (?, 'person', '新しい人物', 'manual')",
            (reference_work_id,),
        )
        connection.commit()
        first_speaker_id = connection.execute(
            "SELECT id FROM style_analysis_runs "
            "WHERE document_id = ? AND analyzer_id = 'speaker-attribution' "
            "ORDER BY id DESC LIMIT 1",
            (document_id,),
        ).fetchone()[0]
        second = DocumentAnalysisOrchestrator(
            connection,
            model_client=_FailingSpeakerModel(),
            model_provider="test",
            model_id="fake",
        ).analyze_document(
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=first.structure_revision_id,
            preset="full",
        )
        second_speaker_id = connection.execute(
            "SELECT id FROM style_analysis_runs "
            "WHERE document_id = ? AND analyzer_id = 'speaker-attribution' "
            "ORDER BY id DESC LIMIT 1",
            (document_id,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE style_analysis_runs SET status = 'partial' WHERE id = ?",
            (second_speaker_id,),
        )
        connection.commit()
        second_speaker_status = connection.execute(
            "SELECT status FROM style_analysis_runs WHERE id = ?",
            (second_speaker_id,),
        ).fetchone()[0]

        semantics = StyleAnalysisCatalogService(connection).get_semantics(
            document_id, first.structure_revision_id
        )

        assert second.status == "succeeded"
        assert second_speaker_status == "partial"
        assert second_speaker_id in semantics["analysis_run_ids"]
        assert first_speaker_id not in semantics["analysis_run_ids"]
        assert semantics["analysis_status"]["semantic"]["state"] == "partial"
    finally:
        connection.close()


def test_semantics_returns_entity_mentions_even_without_resolution(
    data_root: Path,
) -> None:
    connection, document_id, _, first = _create_reference_analysis(data_root)
    try:
        mention_run_id = connection.execute(
            "SELECT id FROM style_analysis_runs "
            "WHERE document_id = ? AND analyzer_id = 'entity-mention-extractor' "
            "ORDER BY id DESC LIMIT 1",
            (document_id,),
        ).fetchone()[0]
        scene_id, block_id, block_start, block_end = connection.execute(
            "SELECT scene_id, id, start_cp, end_cp FROM style_blocks "
            "WHERE structure_revision_id = ? AND scene_id IS NOT NULL "
            "ORDER BY id LIMIT 1",
            (first.structure_revision_id,),
        ).fetchone()
        end_cp = min(block_start + 1, block_end)
        connection.execute(
            "INSERT INTO style_mentions "
            "(structure_revision_id, scene_id, block_id, start_cp, end_cp, surface, "
            "mention_type, entity_type_candidate, canonical_name_candidate, "
            "confidence, analysis_run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                first.structure_revision_id,
                scene_id,
                block_id,
                block_start,
                end_cp,
                "本",
                "proper_name",
                "person",
                "未解決人物",
                0.7,
                mention_run_id,
            ),
        )
        connection.commit()

        semantics = StyleAnalysisCatalogService(connection).get_semantics(
            document_id, first.structure_revision_id
        )

        mention = semantics["mentions"][0]
        assert mention["structure_revision_id"] == first.structure_revision_id
        assert mention["scene_id"] == scene_id
        assert mention["block_id"] == block_id
        assert mention["start_cp"] == block_start
        assert mention["end_cp"] == end_cp
        assert mention["surface"] == "本"
        assert mention["mention_type"] == "proper_name"
        assert mention["entity_type_candidate"] == "person"
        assert mention["canonical_name_candidate"] == "未解決人物"
        assert mention["confidence"] == 0.7
        assert mention["analysis_run_id"] == mention_run_id
    finally:
        connection.close()


def test_effective_semantics_does_not_adopt_turn_taking_only_speaker() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        catalog = StyleAnalysisCatalogService(connection)
        effective = catalog._effective_outputs(
            [
                {
                    "annotation_type": "speaker",
                    "subject_type": "block",
                    "subject_id": 1,
                    "value": {
                        "speaker_entity_id": 7,
                        "evidence_block_ids": [1],
                        "reason_code": "turn_taking",
                    },
                    "confidence": 0.99,
                    "analysis_run_id": 1,
                }
            ]
        )

        assert effective["speakers"][0]["value"]["speaker_entity_id"] is None
        assert effective["speakers"][0]["source"] == "unknown"
    finally:
        connection.close()


def test_effective_semantics_includes_current_mention_resolution_and_novelty() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        catalog = StyleAnalysisCatalogService(connection)
        effective = catalog._effective_outputs(
            [
                {
                    "annotation_type": "mention.entity_resolution",
                    "subject_type": "mention",
                    "subject_id": 10,
                    "value": {"entity_id": 5},
                    "confidence": 0.9,
                    "analysis_run_id": 1,
                },
                {
                    "annotation_type": "term.novelty",
                    "subject_type": "term",
                    "subject_id": 20,
                    "value": {"value": "work_specific"},
                    "confidence": 0.9,
                    "analysis_run_id": 2,
                },
            ],
            mentions=[
                {
                    "id": 10,
                    "surface": "田中",
                    "mention_type": "proper_name",
                    "confidence": 0.9,
                }
            ],
            terms=[{"id": 20, "canonical_label": "用語"}],
        )

        assert effective["mentions"][0]["value"] == {"entity_id": 5}
        assert effective["mentions"][0]["entity_id"] == 5
        assert effective["terms"][0]["novelty"] == "work_specific"
        assert effective["terms"][0]["source"] == "inferred"
    finally:
        connection.close()


def test_effective_term_without_novelty_uses_default_source() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        effective = StyleAnalysisCatalogService(connection)._effective_outputs(
            [], terms=[{"id": 20, "canonical_label": "用語"}]
        )

        assert effective["terms"] == [
            {
                "id": 20,
                "canonical_label": "用語",
                "novelty": "uncertain",
                "value": {"value": "uncertain"},
                "source": "default",
            }
        ]
    finally:
        connection.close()


def test_missing_current_dependency_lineage_is_stale(data_root: Path) -> None:
    connection, document_id, text_revision_id, first = _create_reference_analysis(
        data_root
    )
    try:
        orchestrator = DocumentAnalysisOrchestrator(connection, model_client=None)
        run_id = orchestrator._new_run(
            "entity-mention-extractor",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=first.structure_revision_id,
            reuse=False,
        )
        orchestrator._finish(run_id)
        connection.commit()

        status = StyleAnalysisCatalogService(connection).analysis_status(
            document_id,
            text_revision_id,
            first.structure_revision_id,
        )
        assert status["semantic"] == {
            "state": "stale",
            "reasons": ["CURRENT_RESOLUTION_CHANGED"],
        }
    finally:
        connection.close()


def test_analyzer_version_change_marks_semantic_stale(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, document_id, text_revision_id, first = _create_reference_analysis(
        data_root
    )
    try:
        definition = ANALYZERS_BY_ID["scene-semantic-classifier"]
        monkeypatch.setattr(
            catalog_current_module,
            "ANALYZERS_BY_ID",
            {
                **ANALYZERS_BY_ID,
                "scene-semantic-classifier": replace(
                    definition, version=definition.version + 1
                ),
            },
        )

        status = StyleAnalysisCatalogService(connection).analysis_status(
            document_id,
            text_revision_id,
            first.structure_revision_id,
        )
        assert status["semantic"] == {
            "state": "stale",
            "reasons": ["CURRENT_RESOLUTION_CHANGED"],
        }
    finally:
        connection.close()
