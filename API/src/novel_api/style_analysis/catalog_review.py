from __future__ import annotations

from novel_core.style_analysis.entity_models import EntityAliasRecord, EntityRecord
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.review_models import (
    InferenceReviewRecord,
    ManualOverrideRecord,
    ReviewItemRecord,
)
from novel_core.style_analysis.review_service import ReviewService
from novel_core.style_analysis.term_models import TermAliasRecord, TermRecord
from novel_core.style_analysis.term_service import TermService

from novel_api.style_analysis.job_service import DatabaseConnection

_METRIC_ONLY_OVERRIDE_FIELDS = frozenset(
    {
        "block.speaker_entity_id",
        "block.semantic_primary",
        "term.novelty",
        "term_mention.sufficient_explanation_annotation_id",
    }
)
_METRIC_ONLY_REVIEW_FIELDS = frozenset(
    {
        "block.speaker",
        "block.semantic_primary",
        "term.novelty",
        "term_mention.explanation",
    }
)


class StyleAnalysisReviewMixin:
    _connection: DatabaseConnection
    _entities: EntityService
    _terms: TermService
    _reviews: ReviewService

    def create_entity(
        self,
        *,
        reference_work_id: int | None,
        document_id: int | None,
        entity_type: str,
        canonical_name: str,
    ) -> EntityRecord:
        return self._entities.create_manual_entity(
            reference_work_id=reference_work_id,
            document_id=document_id,
            entity_type=entity_type,
            canonical_name=canonical_name,
        )

    def create_entity_alias(
        self, *, entity_id: int, alias: str, alias_kind: str
    ) -> EntityAliasRecord:
        return self._entities.create_manual_alias(
            entity_id=entity_id, alias=alias, alias_kind=alias_kind
        )

    def link_character(
        self, *, document_id: int, style_entity_id: int, project_character_id: int
    ) -> dict[str, int]:
        return self._entities.link_character(
            document_id=document_id,
            style_entity_id=style_entity_id,
            project_character_id=project_character_id,
        )

    def unlink_character(self, *, document_id: int, project_character_id: int) -> bool:
        return self._entities.unlink_character(
            document_id=document_id, project_character_id=project_character_id
        )

    def create_term(
        self,
        *,
        reference_work_id: int | None,
        document_id: int | None,
        canonical_label: str,
        term_type: str,
    ) -> TermRecord:
        return self._terms.create_manual_term(
            reference_work_id=reference_work_id,
            document_id=document_id,
            canonical_label=canonical_label,
            term_type=term_type,
        )

    def create_term_alias(self, *, term_id: int, alias: str) -> TermAliasRecord:
        return self._terms.create_manual_alias(term_id=term_id, alias=alias)

    def create_override(
        self,
        *,
        subject_type: str,
        subject_id: int,
        field_path: str,
        operation: str,
        value: object = None,
        document_id: int | None = None,
        reference_work_id: int | None = None,
        base_analysis_run_id: int | None = None,
        structure_revision_id: int | None = None,
        note: str | None = None,
    ) -> ManualOverrideRecord:
        return self._reviews.create_override(
            subject_type=subject_type,
            subject_id=subject_id,
            field_path=field_path,
            operation=operation,
            value=value,
            document_id=document_id,
            reference_work_id=reference_work_id,
            base_analysis_run_id=base_analysis_run_id,
            structure_revision_id=structure_revision_id,
            note=note,
        )

    @staticmethod
    def override_correction_class(field_path: str) -> str:
        return (
            "metric_only_recompute"
            if field_path in _METRIC_ONLY_OVERRIDE_FIELDS
            else "semantic_reanalysis_required"
        )

    def create_inference_review(
        self,
        *,
        analysis_run_id: int,
        subject_type: str,
        subject_id: int,
        field_path: str,
        review_status: str,
        note: str | None = None,
    ) -> InferenceReviewRecord:
        return self._reviews.create_inference_review(
            analysis_run_id=analysis_run_id,
            subject_type=subject_type,
            subject_id=subject_id,
            field_path=field_path,
            review_status=review_status,
            note=note,
        )

    @staticmethod
    def inference_review_correction_class(field_path: str) -> str:
        if field_path in _METRIC_ONLY_REVIEW_FIELDS:
            return "metric_only_recompute"
        if field_path == "scene.pov":
            return "display_only"
        if field_path.startswith("scene."):
            return "aggregate_lint_recompute_required"
        return "semantic_reanalysis_required"

    def metric_recompute_target(
        self, record: ManualOverrideRecord | InferenceReviewRecord
    ) -> tuple[str, dict[str, object]] | None:
        if record.document_id is not None:
            row = self._connection.execute(
                "SELECT current_text_revision_id, current_structure_revision_id "
                "FROM style_documents WHERE id=?",
                (record.document_id,),
            ).fetchone()
            if row is None or row[0] is None:
                return None
            return "analyze_document", {
                "document_id": record.document_id,
                "text_revision_id": int(row[0]),
                "structure_revision_id": int(row[1]) if row[1] is not None else None,
                "preset": "metrics",
            }
        if record.reference_work_id is not None:
            return "analyze_reference_work", {
                "reference_work_id": record.reference_work_id,
                "preset": "metrics",
            }
        return None

    def create_review_item(
        self,
        *,
        subject_type: str,
        subject_id: int,
        analysis_run_id: int | None = None,
        priority: str = "normal",
    ) -> ReviewItemRecord:
        return self._reviews.create_manual_review_item(
            subject_type=subject_type,
            subject_id=subject_id,
            analysis_run_id=analysis_run_id,
            priority=priority,
        )

    def list_review_items(
        self, *, status: str | None = None
    ) -> tuple[ReviewItemRecord, ...]:
        return self._reviews.list_review_items(status=status)

    def get_review_item(self, review_item_id: int) -> ReviewItemRecord | None:
        return self._reviews.get_review_item(review_item_id)

    def resolve_review_item(
        self, review_item_id: int, *, expected_version: int, note: str | None
    ) -> ReviewItemRecord:
        return self._reviews.resolve_review_item(
            review_item_id, expected_version=expected_version, note=note
        )

    def ignore_review_item(
        self, review_item_id: int, *, expected_version: int, note: str | None
    ) -> ReviewItemRecord:
        return self._reviews.ignore_review_item(
            review_item_id, expected_version=expected_version, note=note
        )
