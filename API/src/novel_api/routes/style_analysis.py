from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from novel_core.style_analysis.source_models import (
    ReferenceEpisodeRecord,
    ReferenceWorkRecord,
)

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.style_analysis import (
    ReferenceEpisodeResponse,
    ReferenceWorkResponse,
    StyleImportResponse,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)
from novel_api.style_analysis.ingestion_service import (
    MAX_UPLOAD_BYTES,
    import_source,
)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/style-analysis",
    tags=["style-analysis"],
)


@router.post(
    "/imports/file",
    response_model=ProjectEnvelope[StyleImportResponse],
    status_code=201,
)
async def import_file(
    request: Request,
    project_id: str,
    response: Response,
    source_type: str = Form(...),  # noqa: B008
    file: UploadFile = File(...),  # noqa: B008
) -> ProjectEnvelope[StyleImportResponse]:
    target = resolve_project_target(request, project_id)
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        outcome = import_source(
            target,
            source_type=source_type,
            filename=file.filename or "upload",
            payload=payload,
            media_type=file.content_type or "application/octet-stream",
        )
    finally:
        await file.close()
    if outcome.reused_existing:
        response.status_code = 200
    return envelope(
        project_id,
        StyleImportResponse(
            reused_existing=outcome.reused_existing,
            reference_work_id=outcome.reference_work_id,
            source_id=outcome.source_id,
        ),
    )


@router.get(
    "/reference-works",
    response_model=ProjectEnvelope[list[ReferenceWorkResponse]],
)
def list_reference_works(
    request: Request, project_id: str
) -> ProjectEnvelope[list[ReferenceWorkResponse]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        records = services.style_analysis.list_reference_works()
    return envelope(project_id, [_work_response(record) for record in records])


@router.get(
    "/reference-works/{work_id}",
    response_model=ProjectEnvelope[ReferenceWorkResponse],
)
def get_reference_work(
    request: Request, project_id: str, work_id: int
) -> ProjectEnvelope[ReferenceWorkResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        record = services.style_analysis.get_reference_work(work_id)
    if record is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, _work_response(record))


@router.get(
    "/reference-works/{work_id}/episodes",
    response_model=ProjectEnvelope[list[ReferenceEpisodeResponse]],
)
def list_reference_episodes(
    request: Request, project_id: str, work_id: int
) -> ProjectEnvelope[list[ReferenceEpisodeResponse]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_reference_work(work_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        records = services.style_analysis.list_reference_episodes(work_id)
    return envelope(project_id, [_episode_response(record) for record in records])


@router.get(
    "/reference-episodes/{episode_id}",
    response_model=ProjectEnvelope[ReferenceEpisodeResponse],
)
def get_reference_episode(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[ReferenceEpisodeResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        record = services.style_analysis.get_reference_episode(episode_id)
    if record is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, _episode_response(record))


@router.delete("/reference-works/{work_id}", status_code=204)
def delete_reference_work(request: Request, project_id: str, work_id: int) -> Response:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if not services.style_analysis.purge_reference_work(work_id):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
    return Response(status_code=204)


def _work_response(record: ReferenceWorkRecord) -> ReferenceWorkResponse:
    return ReferenceWorkResponse(
        reference_work_id=record.id,
        source_id=record.source_id,
        source_type=record.source_type,
        title=record.title,
        author_name=record.author_name,
        episode_count=record.episode_count,
        created_at=record.created_at,
    )


def _episode_response(record: ReferenceEpisodeRecord) -> ReferenceEpisodeResponse:
    return ReferenceEpisodeResponse(
        reference_episode_id=record.id,
        reference_work_id=record.reference_work_id,
        title=record.title,
        order_index=record.order_index,
        style_document_id=record.style_document_id,
        current_text_revision_id=record.current_text_revision_id,
        current_structure_revision_id=record.current_structure_revision_id,
        current_structure_kind=record.current_structure_kind,
        analysis_status={
            "basic": {"state": "not_analyzed", "reasons": []},
            "semantic": {"state": "not_analyzed", "reasons": []},
        },
    )
