from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response
from novel_core.style_analysis.entity_models import EntityAliasRecord, EntityRecord
from novel_core.style_analysis.fingerprints import JsonObject
from novel_core.style_analysis.review_models import (
    InferenceReviewRecord,
    ManualOverrideRecord,
    ReviewItemRecord,
)
from novel_core.style_analysis.runtime_models import JobRecord, JobType
from novel_core.style_analysis.term_models import TermAliasRecord, TermRecord

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.style_analysis import (
    CharacterLinkRequest,
    CharacterLinkResponse,
    InferenceReviewRequest,
    InferenceReviewResponse,
    ReviewItemActionRequest,
    ReviewItemCreateRequest,
    ReviewItemResponse,
    StyleEntityAliasRequest,
    StyleEntityAliasResponse,
    StyleEntityCreateRequest,
    StyleEntityResponse,
    StyleJobResponse,
    StyleOverrideRequest,
    StyleOverrideResponse,
    StyleTermAliasRequest,
    StyleTermAliasResponse,
    StyleTermCreateRequest,
    StyleTermResponse,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)
from novel_api.style_analysis.job_service import StyleJobService

router = APIRouter()


@router.post(
    "/entities", response_model=ProjectEnvelope[StyleEntityResponse], status_code=201
)
def create_style_entity(
    request: Request, project_id: str, payload: StyleEntityCreateRequest
) -> ProjectEnvelope[StyleEntityResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        record = services.style_analysis.create_entity(**payload.model_dump())
    return envelope(project_id, _entity_response(record))


@router.post(
    "/entities/{entity_id}/aliases",
    response_model=ProjectEnvelope[StyleEntityAliasResponse],
    status_code=201,
)
def create_style_entity_alias(
    request: Request,
    project_id: str,
    entity_id: int,
    payload: StyleEntityAliasRequest,
) -> ProjectEnvelope[StyleEntityAliasResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        record = services.style_analysis.create_entity_alias(
            entity_id=entity_id, **payload.model_dump()
        )
    return envelope(project_id, _entity_alias_response(record))


@router.post(
    "/terms", response_model=ProjectEnvelope[StyleTermResponse], status_code=201
)
def create_style_term(
    request: Request, project_id: str, payload: StyleTermCreateRequest
) -> ProjectEnvelope[StyleTermResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        record = services.style_analysis.create_term(**payload.model_dump())
    return envelope(project_id, _term_response(record))


@router.post(
    "/terms/{term_id}/aliases",
    response_model=ProjectEnvelope[StyleTermAliasResponse],
    status_code=201,
)
def create_style_term_alias(
    request: Request,
    project_id: str,
    term_id: int,
    payload: StyleTermAliasRequest,
) -> ProjectEnvelope[StyleTermAliasResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        record = services.style_analysis.create_term_alias(
            term_id=term_id, **payload.model_dump()
        )
    return envelope(project_id, _term_alias_response(record))


@router.put(
    "/documents/{document_id}/character-links/{project_character_id}",
    response_model=ProjectEnvelope[CharacterLinkResponse],
)
def link_style_character(
    request: Request,
    project_id: str,
    document_id: int,
    project_character_id: int,
    payload: CharacterLinkRequest,
) -> ProjectEnvelope[CharacterLinkResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        link = services.style_analysis.link_character(
            document_id=document_id,
            project_character_id=project_character_id,
            style_entity_id=payload.style_entity_id,
        )
    return envelope(project_id, link)


@router.delete(
    "/documents/{document_id}/character-links/{project_character_id}", status_code=204
)
def unlink_style_character(
    request: Request, project_id: str, document_id: int, project_character_id: int
) -> Response:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        services.style_analysis.unlink_character(
            document_id=document_id, project_character_id=project_character_id
        )
    return Response(status_code=204)


@router.post(
    "/overrides",
    response_model=ProjectEnvelope[StyleOverrideResponse],
    status_code=201,
)
def create_style_override(
    request: Request, project_id: str, payload: StyleOverrideRequest
) -> ProjectEnvelope[StyleOverrideResponse]:
    target = resolve_project_target(request, project_id)
    values = payload.model_dump()
    with open_project_services(target) as services:
        record = services.style_analysis.create_override(**values)
        correction_class = services.style_analysis.override_correction_class(
            payload.field_path
        )
        job_target = (
            services.style_analysis.metric_recompute_target(record)
            if correction_class == "metric_only_recompute"
            else None
        )
    job = _enqueue_metric_job(request, project_id, job_target)
    return envelope(
        project_id,
        _override_response(record, correction_class=correction_class, job=job),
    )


@router.post(
    "/inference-reviews",
    response_model=ProjectEnvelope[InferenceReviewResponse],
    status_code=201,
)
def create_style_inference_review(
    request: Request, project_id: str, payload: InferenceReviewRequest
) -> ProjectEnvelope[InferenceReviewResponse]:
    target = resolve_project_target(request, project_id)
    values = payload.model_dump()
    with open_project_services(target) as services:
        record = services.style_analysis.create_inference_review(**values)
        correction_class = services.style_analysis.inference_review_correction_class(
            payload.field_path
        )
        job_target = (
            services.style_analysis.metric_recompute_target(record)
            if correction_class == "metric_only_recompute"
            else None
        )
    job = _enqueue_metric_job(request, project_id, job_target)
    return envelope(
        project_id,
        _inference_review_response(record, correction_class=correction_class, job=job),
    )


@router.get("/review-items", response_model=ProjectEnvelope[list[ReviewItemResponse]])
def list_style_review_items(
    request: Request, project_id: str, status: str | None = None
) -> ProjectEnvelope[list[ReviewItemResponse]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        items = services.style_analysis.list_review_items(status=status)
    return envelope(project_id, [_review_item_response(item) for item in items])


@router.get(
    "/review-items/{review_item_id}",
    response_model=ProjectEnvelope[ReviewItemResponse],
)
def get_style_review_item(
    request: Request, project_id: str, review_item_id: int
) -> ProjectEnvelope[ReviewItemResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        item = services.style_analysis.get_review_item(review_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, _review_item_response(item))


@router.post(
    "/review-items",
    response_model=ProjectEnvelope[ReviewItemResponse],
    status_code=201,
)
def create_style_review_item(
    request: Request, project_id: str, payload: ReviewItemCreateRequest
) -> ProjectEnvelope[ReviewItemResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        item = services.style_analysis.create_review_item(**payload.model_dump())
    return envelope(project_id, _review_item_response(item))


@router.post(
    "/review-items/{review_item_id}/resolve",
    response_model=ProjectEnvelope[ReviewItemResponse],
)
def resolve_style_review_item(
    request: Request,
    project_id: str,
    review_item_id: int,
    payload: ReviewItemActionRequest,
) -> ProjectEnvelope[ReviewItemResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        item = services.style_analysis.resolve_review_item(
            review_item_id, **payload.model_dump()
        )
    return envelope(project_id, _review_item_response(item))


@router.post(
    "/review-items/{review_item_id}/ignore",
    response_model=ProjectEnvelope[ReviewItemResponse],
)
def ignore_style_review_item(
    request: Request,
    project_id: str,
    review_item_id: int,
    payload: ReviewItemActionRequest,
) -> ProjectEnvelope[ReviewItemResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        item = services.style_analysis.ignore_review_item(
            review_item_id, **payload.model_dump()
        )
    return envelope(project_id, _review_item_response(item))


def _enqueue_metric_job(
    request: Request,
    project_id: str,
    job_target: tuple[str, dict[str, object]] | None,
) -> JobRecord | None:
    if job_target is None:
        return None
    return StyleJobService(
        data_root=request.app.state.settings.data_root,
        notify=request.app.state.style_analysis_worker.notify,
    ).enqueue(project_id, cast(JobType, job_target[0]), cast(JsonObject, job_target[1]))


def _entity_response(record: EntityRecord) -> StyleEntityResponse:
    return StyleEntityResponse(
        id=record.id,
        document_id=record.document_id,
        reference_work_id=record.reference_work_id,
        entity_type=record.entity_type,
        canonical_name=record.canonical_name,
        origin=record.origin,
        created_by_run_id=record.created_by_run_id,
        created_at=record.created_at,
    )


def _entity_alias_response(record: EntityAliasRecord) -> StyleEntityAliasResponse:
    return StyleEntityAliasResponse(
        id=record.id,
        entity_id=record.entity_id,
        alias=record.alias,
        alias_kind=record.alias_kind,
        origin=record.origin,
        analysis_run_id=record.analysis_run_id,
        source_mention_id=record.source_mention_id,
        created_at=record.created_at,
    )


def _term_response(record: TermRecord) -> StyleTermResponse:
    return StyleTermResponse(
        id=record.id,
        document_id=record.document_id,
        reference_work_id=record.reference_work_id,
        canonical_label=record.canonical_label,
        term_type=record.term_type,
        origin=record.origin,
        created_by_run_id=record.created_by_run_id,
        created_at=record.created_at,
    )


def _term_alias_response(record: TermAliasRecord) -> StyleTermAliasResponse:
    return StyleTermAliasResponse(
        id=record.id,
        term_id=record.term_id,
        alias=record.alias,
        origin=record.origin,
        analysis_run_id=record.analysis_run_id,
        created_at=record.created_at,
    )


def _override_response(
    record: ManualOverrideRecord,
    *,
    correction_class: str,
    job: JobRecord | None,
) -> StyleOverrideResponse:
    value = json.loads(record.value_json) if record.value_json is not None else None
    return StyleOverrideResponse(
        id=record.id,
        document_id=record.document_id,
        reference_work_id=record.reference_work_id,
        subject_type=record.subject_type,
        subject_id=record.subject_id,
        field_path=record.field_path,
        operation=record.operation,
        value=value,
        base_analysis_run_id=record.base_analysis_run_id,
        structure_revision_id=record.structure_revision_id,
        note=record.note,
        created_at=record.created_at,
        correction_class=correction_class,
        job_id=job.id if job is not None else None,
    )


def _inference_review_response(
    record: InferenceReviewRecord,
    *,
    correction_class: str,
    job: JobRecord | None,
) -> InferenceReviewResponse:
    return InferenceReviewResponse(
        id=record.id,
        document_id=record.document_id,
        reference_work_id=record.reference_work_id,
        subject_type=record.subject_type,
        subject_id=record.subject_id,
        field_path=record.field_path,
        analysis_run_id=record.analysis_run_id,
        review_status=record.review_status,
        note=record.note,
        created_at=record.created_at,
        correction_class=correction_class,
        job_id=job.id if job is not None else None,
    )


def _review_item_response(record: ReviewItemRecord) -> ReviewItemResponse:
    evidence = json.loads(record.evidence_json)
    return ReviewItemResponse(
        id=record.id,
        document_id=record.document_id,
        reference_work_id=record.reference_work_id,
        item_type=record.item_type,
        subject_type=record.subject_type,
        subject_id=record.subject_id,
        analysis_run_id=record.analysis_run_id,
        priority=record.priority,
        status=record.status,
        reason_code=record.reason_code,
        evidence=evidence if isinstance(evidence, dict) else {},
        resolution_note=record.resolution_note,
        version=record.version,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
    )


def _job_response(job: JobRecord) -> StyleJobResponse:
    result = json.loads(job.result_json)
    warnings = json.loads(job.warning_json)
    return StyleJobResponse(
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress={"current": job.progress_current, "total": job.progress_total},
        result=result if isinstance(result, dict) else {},
        warnings=warnings if isinstance(warnings, list) else [],
        error_code=job.error_code,
        error_message=job.error_message,
    )
