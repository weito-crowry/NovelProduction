from __future__ import annotations

from pathlib import Path

import pytest
from test_style_analysis_semantic_metrics import _fixture

from novel_core.services.character_service import CharacterService
from novel_core.style_analysis import review_service_core
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.review_service import ReviewService
from novel_core.style_analysis.term_service import TermService


def test_manual_review_item_has_fixed_defaults_and_scope_evidence(
    tmp_path: Path,
) -> None:
    connection, document_id, scenes, _ = _fixture(tmp_path)
    try:
        service = ReviewService(connection)
        item = service.create_manual_review_item(
            subject_type="scene", subject_id=scenes[0].id, priority="high"
        )
        assert item.document_id == document_id
        assert item.reference_work_id is None
        assert item.item_type == "manual_review"
        assert item.status == "open"
        assert item.reason_code == "user_marked"
        assert item.priority == "high"
        assert item.version == 1
        assert item.resolution_note is None
        assert item.resolved_at is None
        assert '"text"' not in item.evidence_json
        assert f'"scene_id":{scenes[0].id}' in item.evidence_json
    finally:
        connection.close()


def test_review_item_resolution_uses_expected_version_and_rejects_closed_item(
    tmp_path: Path,
) -> None:
    connection, _, scenes, _ = _fixture(tmp_path)
    try:
        service = ReviewService(connection)
        item = service.create_manual_review_item(
            subject_type="scene", subject_id=scenes[0].id
        )
        with pytest.raises(ValueError, match="VERSION_CONFLICT"):
            service.resolve_review_item(item.id, expected_version=2, note="late")
        resolved = service.resolve_review_item(
            item.id, expected_version=1, note="確認済み"
        )
        assert resolved.status == "resolved"
        assert resolved.version == 2
        assert resolved.resolution_note == "確認済み"
        with pytest.raises(ValueError, match="REVIEW_ITEM_CLOSED"):
            service.ignore_review_item(item.id, expected_version=2, note=None)
    finally:
        connection.close()


def test_manual_override_is_append_only_and_revert_falls_back(
    tmp_path: Path,
) -> None:
    connection, document_id, _, blocks = _fixture(tmp_path)
    try:
        service = ReviewService(connection)
        first = service.create_override(
            subject_type="block",
            subject_id=blocks[0].id,
            field_path="block.speaker_entity_id",
            operation="set",
            value=1,
            document_id=document_id,
            structure_revision_id=1,
        )
        reverted = service.create_override(
            subject_type="block",
            subject_id=blocks[0].id,
            field_path="block.speaker_entity_id",
            operation="revert",
            document_id=document_id,
            structure_revision_id=1,
        )
        assert first.id < reverted.id
        assert reverted.operation == "revert"
        assert reverted.value_json is None
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_manual_overrides "
                "WHERE subject_type = 'block' AND subject_id = ?",
                (blocks[0].id,),
            ).fetchone()[0]
            == 2
        )
        with pytest.raises(ValueError, match="OVERRIDE_NOT_FOUND"):
            service.create_override(
                subject_type="block",
                subject_id=blocks[0].id,
                field_path="block.speaker_entity_id",
                operation="revert",
                document_id=document_id,
                structure_revision_id=1,
            )
    finally:
        connection.close()


def test_inference_review_requires_registered_current_raw_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, _, _, blocks = _fixture(tmp_path)
    try:
        monkeypatch.setattr(
            review_service_core.CurrentRunResolver,
            "resolve",
            lambda resolver, *args: resolver.runs.get_run(2),
        )
        service = ReviewService(connection)
        review = service.create_inference_review(
            analysis_run_id=2,
            subject_type="block",
            subject_id=blocks[0].id,
            field_path="block.speaker",
            review_status="confirmed",
        )
        assert review.review_status == "confirmed"
        with pytest.raises(ValueError, match="INFERENCE_REVIEW_TARGET_INVALID"):
            service.create_inference_review(
                analysis_run_id=2,
                subject_type="block",
                subject_id=blocks[0].id,
                field_path="block.unknown",
                review_status="confirmed",
            )
        with pytest.raises(ValueError, match="INFERENCE_REVIEW_SOURCE_NOT_FOUND"):
            service.create_inference_review(
                analysis_run_id=2,
                subject_type="scene",
                subject_id=1,
                field_path="scene.function",
                review_status="confirmed",
            )
    finally:
        connection.close()


def test_inference_review_rejects_historical_run_even_with_matching_raw_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, document_id, _, blocks = _fixture(tmp_path)
    try:
        historical_id = AnalysisRunRepository(connection).insert_run(
            document_id=document_id,
            analyzer_id="speaker-attribution",
            analyzer_version=1,
            text_revision_id=1,
            structure_revision_id=1,
            status="succeeded",
            fingerprint="a" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:01+00:00",
        )
        monkeypatch.setattr(
            review_service_core.CurrentRunResolver,
            "resolve",
            lambda resolver, *args: resolver.runs.get_run(2),
        )
        with pytest.raises(ValueError, match="INFERENCE_REVIEW_SOURCE_NOT_FOUND"):
            ReviewService(connection).create_inference_review(
                analysis_run_id=historical_id,
                subject_type="block",
                subject_id=blocks[0].id,
                field_path="block.speaker",
                review_status="confirmed",
            )
    finally:
        connection.close()


def test_manual_identity_alias_is_scoped_and_alias_creation_is_idempotent(
    tmp_path: Path,
) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        entity_service = EntityService(connection)
        entity = entity_service.create_manual_entity(
            reference_work_id=None,
            document_id=document_id,
            entity_type="person",
            canonical_name="  手動人物  ",
        )
        alias = entity_service.create_manual_alias(
            entity_id=entity.id, alias=" 別名 ", alias_kind="name"
        )
        same_alias = entity_service.create_manual_alias(
            entity_id=entity.id, alias="別名", alias_kind="name"
        )
        assert entity.origin == "manual"
        assert entity.canonical_name == "手動人物"
        assert alias.id == same_alias.id
        assert alias.origin == "manual"

        term_service = TermService(connection)
        term = term_service.create_manual_term(
            reference_work_id=None,
            document_id=document_id,
            canonical_label="  手動用語  ",
            term_type="other",
        )
        term_alias = term_service.create_manual_alias(
            term_id=term.id, alias=" 用語別名 "
        )
        assert term.origin == "manual"
        assert term.canonical_label == "手動用語"
        assert term_alias.origin == "manual"
        assert (
            term_service.create_manual_alias(term_id=term.id, alias="用語別名").id
            == term_alias.id
        )
    finally:
        connection.close()


def test_character_link_requires_project_document_person_and_enabled_entity(
    tmp_path: Path,
) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        entity_service = EntityService(connection)
        entity = entity_service.create_manual_entity(
            reference_work_id=None,
            document_id=document_id,
            entity_type="person",
            canonical_name="人物",
        )
        character = CharacterService(connection).create("人物")
        link = entity_service.link_character(
            document_id=document_id,
            style_entity_id=entity.id,
            project_character_id=character.id,
        )
        assert link["document_id"] == document_id
        assert link["style_entity_id"] == entity.id
        assert link["project_character_id"] == character.id
        assert entity_service.unlink_character(
            document_id=document_id, project_character_id=character.id
        )
    finally:
        connection.close()
