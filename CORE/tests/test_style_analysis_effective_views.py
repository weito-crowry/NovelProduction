from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_style_analysis_semantic_metrics import _fixture

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.review_service import ReviewService
from novel_core.style_analysis.semantic_metric_support import (
    enabled_person,
    resolve_entity_enabled,
    resolve_entity_name,
    resolve_entity_type,
    resolve_mention_entity,
    resolve_speaker,
    resolve_term_mention_explanation,
    resolve_term_novelty,
)
from novel_core.style_analysis.semantic_repository import SemanticRepository
from novel_core.style_analysis.semantic_scene import resolve_scene_semantics
from novel_core.style_analysis.term_service import TermService


def test_typed_identity_resolvers_honor_manual_then_revert_to_stable_row(
    tmp_path: Path,
) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        entity_id = connection.execute(
            "SELECT id FROM style_entities WHERE canonical_name='A'"
        ).fetchone()[0]
        service = ReviewService(connection)
        service.create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.canonical_name",
            operation="set",
            value="B",
            document_id=document_id,
        )
        service.create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.canonical_name",
            operation="set",
            value="C",
            document_id=document_id,
        )
        service.create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.canonical_name",
            operation="revert",
            document_id=document_id,
        )
        assert resolve_entity_name(connection, entity_id).value == "A"
        with pytest.raises(ValueError, match="OVERRIDE_NOT_FOUND"):
            service.create_override(
                subject_type="entity",
                subject_id=entity_id,
                field_path="entity.canonical_name",
                operation="revert",
                document_id=document_id,
            )
        service.create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.entity_type",
            operation="set",
            value="other",
            document_id=document_id,
        )
        service.create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.enabled",
            operation="set",
            value=False,
            document_id=document_id,
        )
        assert resolve_entity_name(connection, entity_id).value == "A"
        assert resolve_entity_type(connection, entity_id).value == "other"
        assert resolve_entity_enabled(connection, entity_id).value is False
        with pytest.raises(ValueError, match="OVERRIDE_CLEAR_INVALID"):
            service.create_override(
                subject_type="entity",
                subject_id=entity_id,
                field_path="entity.enabled",
                operation="clear",
                document_id=document_id,
            )
    finally:
        connection.close()


def test_inferred_alias_reviews_control_entity_and_term_resolvers(
    tmp_path: Path,
) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        entity_service = EntityService(connection)
        entity_id = int(
            connection.execute(
                "SELECT id FROM style_entities WHERE canonical_name='A'"
            ).fetchone()[0]
        )
        entity_alias = entity_service.repository.insert_alias(
            entity_id=entity_id,
            alias="人物別名",
            alias_kind="name",
            origin="inferred",
            analysis_run_id=1,
        )
        term_service = TermService(connection)
        term = term_service.create_manual_term(
            reference_work_id=None,
            document_id=document_id,
            canonical_label="用語",
            term_type="other",
        )
        term_alias = term_service.repository.insert_alias(
            term_id=term.id,
            alias="用語別名",
            origin="inferred",
            analysis_run_id=1,
        )
        connection.commit()
        reviews = ReviewService(connection)
        reviews.create_inference_review(
            analysis_run_id=1,
            subject_type="entity_alias",
            subject_id=entity_alias.id,
            field_path="entity_alias.acceptance",
            review_status="confirmed",
        )
        reviews.create_inference_review(
            analysis_run_id=1,
            subject_type="term_alias",
            subject_id=term_alias.id,
            field_path="term_alias.acceptance",
            review_status="confirmed",
        )
        assert entity_service.exact_matches(
            document_id=document_id, surface="人物別名"
        ) == (entity_service.repository.get(entity_id),)
        assert term_service.exact_matches(
            document_id=document_id, surface="用語別名"
        ) == (term_service.repository.get(term.id),)
        reviews.create_inference_review(
            analysis_run_id=1,
            subject_type="entity_alias",
            subject_id=entity_alias.id,
            field_path="entity_alias.acceptance",
            review_status="rejected",
        )
        reviews.create_inference_review(
            analysis_run_id=1,
            subject_type="term_alias",
            subject_id=term_alias.id,
            field_path="term_alias.acceptance",
            review_status="rejected",
        )
        assert (
            entity_service.exact_matches(document_id=document_id, surface="人物別名")
            == ()
        )
        assert (
            term_service.exact_matches(document_id=document_id, surface="用語別名")
            == ()
        )
    finally:
        connection.close()


def test_candidate_rows_use_effective_entity_and_term_types(tmp_path: Path) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        entity_service = EntityService(connection)
        entity_id = int(
            connection.execute(
                "SELECT id FROM style_entities WHERE canonical_name='A'"
            ).fetchone()[0]
        )
        term_service = TermService(connection)
        term = term_service.create_manual_term(
            reference_work_id=None,
            document_id=document_id,
            canonical_label="用語",
            term_type="other",
        )
        reviews = ReviewService(connection)
        reviews.create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.entity_type",
            operation="set",
            value="organization",
            document_id=document_id,
        )
        reviews.create_override(
            subject_type="term",
            subject_id=term.id,
            field_path="term.term_type",
            operation="set",
            value="technology",
            document_id=document_id,
        )
        entity_rows = entity_service.candidate_rows(
            document_id=document_id,
            entity_type="organization",
            surface="",
            same_scene_ids=set(),
        )
        term_rows = term_service.candidate_rows(
            document_id=document_id,
            term_type="technology",
            same_scene_ids=set(),
        )
        assert {row["entity_id"] for row in entity_rows} == {entity_id}
        assert entity_rows[0]["entity_type"] == "organization"
        assert {row["term_id"] for row in term_rows} == {term.id}
        assert term_rows[0]["term_type"] == "technology"
    finally:
        connection.close()


def test_disabled_entity_is_unknown_for_speaker_effective_value(
    tmp_path: Path,
) -> None:
    connection, document_id, _, blocks = _fixture(tmp_path)
    try:
        entity_id = int(
            connection.execute(
                "SELECT id FROM style_entities WHERE canonical_name='A'"
            ).fetchone()[0]
        )
        assert enabled_person(connection, entity_id)
        ReviewService(connection).create_override(
            subject_type="block",
            subject_id=blocks[1].id,
            field_path="block.speaker_entity_id",
            operation="set",
            value=entity_id,
            document_id=document_id,
            structure_revision_id=1,
        )
        ReviewService(connection).create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.enabled",
            operation="set",
            value=False,
            document_id=document_id,
        )
        raw = (json.dumps({"speaker_entity_id": entity_id}), 1.0, None)
        result = resolve_speaker(connection, blocks[0].id, 2, raw, 0.85)
        assert result.value is None
        assert result.source == "unknown"
        manual_result = resolve_speaker(connection, blocks[1].id, 2, None, 0.85)
        assert manual_result.value is None
        assert manual_result.source == "unknown"
    finally:
        connection.close()


def test_scene_effective_resolver_honors_override_and_disabled_pov_entity(
    tmp_path: Path,
) -> None:
    connection, document_id, scenes, _ = _fixture(tmp_path)
    try:
        scene_id = scenes[0].id
        entity_id = int(
            connection.execute(
                "SELECT id FROM style_entities WHERE canonical_name='A'"
            ).fetchone()[0]
        )
        run_id = AnalysisRunRepository(connection).insert_run(
            document_id=document_id,
            analyzer_id="scene-semantic-classifier",
            analyzer_version=1,
            text_revision_id=1,
            structure_revision_id=1,
            status="succeeded",
            fingerprint="8" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        raw = {
            "scene.function": (
                '{"labels":[{"label":"daily","confidence":1.0}]}',
                1.0,
                None,
            ),
            "scene.pov": (
                json.dumps({"pov_mode": "third_limited", "pov_entity_id": entity_id}),
                1.0,
                None,
            ),
        }
        reviews = ReviewService(connection)
        reviews.create_override(
            subject_type="scene",
            subject_id=scene_id,
            field_path="scene.function",
            operation="set",
            value=["action"],
            document_id=document_id,
            structure_revision_id=1,
        )
        reviews.create_override(
            subject_type="entity",
            subject_id=entity_id,
            field_path="entity.enabled",
            operation="set",
            value=False,
            document_id=document_id,
        )
        effective = resolve_scene_semantics(
            connection,
            scene_id,
            run_id,
            raw,
            structure_revision_id=1,
        )
        assert effective["scene.function"].value == {"labels": [{"label": "action"}]}
        assert effective["scene.function"].source == "manual"
        assert effective["scene.pov"].value == {
            "pov_mode": "third_limited",
            "pov_entity_id": None,
        }
    finally:
        connection.close()


def test_missing_raw_inference_is_unknown_not_inferred(tmp_path: Path) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        mention = resolve_mention_entity(connection, 999, 1, None)
        explanation = resolve_term_mention_explanation(connection, 999, 1, 0.85)
        assert mention.source == "unknown"
        assert explanation.source == "unknown"
        assert document_id > 0
    finally:
        connection.close()


def test_scene_low_confidence_raw_is_unclear_and_confirmed_labels_keep_raw_value(
    tmp_path: Path,
) -> None:
    connection, document_id, scenes, _ = _fixture(tmp_path)
    try:
        scene_id = scenes[0].id
        run_id = AnalysisRunRepository(connection).insert_run(
            document_id=document_id,
            analyzer_id="scene-semantic-classifier",
            analyzer_version=1,
            text_revision_id=1,
            structure_revision_id=1,
            status="succeeded",
            fingerprint="9" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        semantic = SemanticRepository(connection)
        semantic.insert_annotation(
            annotation_type="scene.pace",
            subject_type="scene",
            subject_id=scene_id,
            value_json='{"label":"fast"}',
            confidence=0.5,
            analysis_run_id=run_id,
        )
        semantic.insert_annotation(
            annotation_type="scene.function",
            subject_type="scene",
            subject_id=scene_id,
            value_json='{"labels":[{"label":"action","confidence":0.3}]}',
            confidence=0.3,
            analysis_run_id=run_id,
        )
        connection.execute(
            "INSERT INTO style_inference_reviews "
            "(document_id, subject_type, subject_id, field_path, analysis_run_id, "
            "review_status) VALUES (?, 'scene', ?, 'scene.function', ?, 'confirmed')",
            (document_id, scene_id, run_id),
        )
        connection.commit()
        result = resolve_scene_semantics(
            connection,
            scene_id,
            run_id,
            {
                "scene.pace": ('{"label":"fast"}', 0.5, None),
                "scene.function": (
                    '{"labels":[{"label":"action","confidence":0.3}]}',
                    0.3,
                    None,
                ),
            },
            structure_revision_id=1,
        )
        assert result["scene.pace"].value == {"label": "unclear"}
        assert result["scene.pace"].source == "inferred"
        assert result["scene.function"].value == {
            "labels": [{"label": "action", "confidence": 0.3}]
        }
        assert result["scene.function"].source == "confirmed"
    finally:
        connection.close()


def test_people_for_scene_uses_effective_mention_entity(tmp_path: Path) -> None:
    connection, document_id, scenes, blocks = _fixture(tmp_path)
    try:
        entity_service = EntityService(connection)
        entity_id = int(
            connection.execute(
                "SELECT id FROM style_entities WHERE canonical_name='A'"
            ).fetchone()[0]
        )
        replacement = entity_service.create_manual_entity(
            reference_work_id=None,
            document_id=document_id,
            entity_type="person",
            canonical_name="B",
        )
        connection.execute(
            "INSERT INTO style_mentions "
            "(structure_revision_id, scene_id, block_id, start_cp, end_cp, "
            "surface, mention_type, entity_type_candidate, canonical_name_candidate, "
            "confidence, analysis_run_id) VALUES (?, ?, ?, 0, 1, 'A', 'proper_name', "
            "'person', 'A', 1.0, 1)",
            (1, scenes[0].id, blocks[0].id),
        )
        connection.commit()
        orchestrator = DocumentAnalysisOrchestrator(connection, model_client=None)
        initial = orchestrator._people_for_scene(document_id, 1, scenes[0].id)
        assert [item["entity_id"] for item in initial] == [entity_id]
        ReviewService(connection).create_override(
            subject_type="mention",
            subject_id=1,
            field_path="mention.entity_id",
            operation="set",
            value=replacement.id,
            document_id=document_id,
            structure_revision_id=1,
        )
        effective = orchestrator._people_for_scene(document_id, 1, scenes[0].id)
        assert [item["entity_id"] for item in effective] == [replacement.id]
    finally:
        connection.close()


def test_term_novelty_uses_confirmed_and_rejected_current_reviews(
    tmp_path: Path,
) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        cursor = connection.execute(
            "INSERT INTO style_terms "
            "(document_id, canonical_label, term_type, origin) "
            "VALUES (?, '用語', 'other', 'manual')",
            (document_id,),
        )
        term_id = int(cursor.lastrowid)
        term_run_id = AnalysisRunRepository(connection).insert_run(
            document_id=document_id,
            analyzer_id="term-resolver",
            analyzer_version=1,
            text_revision_id=1,
            structure_revision_id=1,
            status="succeeded",
            fingerprint="9" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        connection.execute(
            "INSERT INTO style_annotations "
            "(annotation_type, subject_type, subject_id, value_json, confidence, "
            "analysis_run_id) "
            "VALUES ('term.novelty', 'term', ?, ?, 0.1, ?)",
            (term_id, json.dumps({"value": "work_specific"}), term_run_id),
        )
        connection.commit()
        raw = (term_id, '{"value":"work_specific"}', 0.1, None)
        connection.execute(
            "INSERT INTO style_inference_reviews "
            "(document_id, subject_type, subject_id, field_path, analysis_run_id, "
            "review_status) VALUES (?, 'term', ?, 'term.novelty', ?, 'confirmed')",
            (document_id, term_id, term_run_id),
        )
        assert (
            resolve_term_novelty(connection, term_id, term_run_id, raw).source
            == "confirmed"
        )
        connection.execute(
            "INSERT INTO style_inference_reviews "
            "(document_id, subject_type, subject_id, field_path, analysis_run_id, "
            "review_status) VALUES (?, 'term', ?, 'term.novelty', ?, 'rejected')",
            (document_id, term_id, term_run_id),
        )
        assert (
            resolve_term_novelty(connection, term_id, term_run_id, raw).source
            == "unknown"
        )
    finally:
        connection.close()
