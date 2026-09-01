from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_style_analysis_semantic_metrics import _fixture

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.review_service import ReviewService
from novel_core.style_analysis.semantic_metric_support import (
    resolve_entity_enabled,
    resolve_entity_name,
    resolve_entity_type,
    resolve_term_novelty,
)


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
        assert resolve_entity_name(connection, entity_id).value == "B"
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
        service = ReviewService(connection)
        service.create_inference_review(
            analysis_run_id=term_run_id,
            subject_type="term",
            subject_id=term_id,
            field_path="term.novelty",
            review_status="confirmed",
        )
        assert (
            resolve_term_novelty(connection, term_id, term_run_id, raw).source
            == "confirmed"
        )
        service.create_inference_review(
            analysis_run_id=term_run_id,
            subject_type="term",
            subject_id=term_id,
            field_path="term.novelty",
            review_status="rejected",
        )
        assert (
            resolve_term_novelty(connection, term_id, term_run_id, raw).source
            == "unknown"
        )
    finally:
        connection.close()
