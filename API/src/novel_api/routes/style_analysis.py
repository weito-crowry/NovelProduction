from __future__ import annotations

import json

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from novel_core.errors import AnalyzerProviderUnavailableError
from novel_core.style_analysis.runtime_models import JobRecord
from novel_core.style_analysis.source_models import (
    ReferenceEpisodeRecord,
    ReferenceWorkRecord,
)

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope
from novel_api.routes.style_analysis_corpus_profile import (
    router as corpus_profile_router,
)
from novel_api.routes.style_analysis_documents import router as documents_router
from novel_api.routes.style_analysis_review import router as review_router
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.style_analysis import (
    ProjectDraftCaptureRequest,
    ReferenceEpisodeResponse,
    ReferenceWorkResponse,
    StyleAnalyzeRequest,
    StyleFindingReviewRequest,
    StyleImportResponse,
    StyleJobResponse,
    StyleLintRequest,
    StyleWorkAnalyzeRequest,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)
from novel_api.style_analysis.ingestion_service import (
    MAX_UPLOAD_BYTES,
    import_source,
)
from novel_api.style_analysis.job_service import StyleJobService

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/style-analysis",
    tags=["style-analysis"],
)


@router.post(
    "/project-episodes/{episode_id}/capture",
    response_model=ProjectEnvelope[dict[str, object]],
)
def capture_project_episode(
    request: Request,
    project_id: str,
    episode_id: int,
    payload: ProjectDraftCaptureRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.capture_project_draft(
            episode_id=episode_id, draft_id=payload.draft_id
        )
    return envelope(project_id, result)


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
        status_by_document = {
            record.style_document_id: services.style_analysis.analysis_status(
                record.style_document_id,
                record.current_text_revision_id,
                record.current_structure_revision_id,
            )
            for record in records
            if record.style_document_id is not None
        }
    return envelope(
        project_id,
        [
            _episode_response(
                record,
                status_by_document.get(record.style_document_id)
                if record.style_document_id is not None
                else None,
            )
            for record in records
        ],
    )


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
        status = (
            services.style_analysis.analysis_status(
                record.style_document_id,
                record.current_text_revision_id,
                record.current_structure_revision_id,
            )
            if record is not None and record.style_document_id is not None
            else None
        )
    if record is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, _episode_response(record, status))


@router.delete("/reference-works/{work_id}", status_code=204)
def delete_reference_work(request: Request, project_id: str, work_id: int) -> Response:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if not services.style_analysis.purge_reference_work(work_id):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
    return Response(status_code=204)


@router.post(
    "/documents/{document_id}/analyze",
    response_model=ProjectEnvelope[StyleJobResponse],
    status_code=202,
)
def analyze_document(
    request: Request,
    project_id: str,
    document_id: int,
    payload: StyleAnalyzeRequest,
) -> ProjectEnvelope[StyleJobResponse]:
    if (
        payload.preset == "full"
        and request.app.state.settings.style_model_provider == "disabled"
    ):
        raise AnalyzerProviderUnavailableError()
    target = resolve_project_target(request, project_id)
    with open_project_services(target):
        pass
    service = StyleJobService(
        data_root=request.app.state.settings.data_root,
        notify=request.app.state.style_analysis_worker.notify,
    )
    job = service.enqueue(
        project_id,
        "analyze_document",
        {"document_id": document_id, **payload.model_dump(exclude_none=True)},
    )
    return envelope(project_id, _job_response(job))


@router.post(
    "/reference-works/{work_id}/analyze",
    response_model=ProjectEnvelope[StyleJobResponse],
    status_code=202,
)
def analyze_reference_work(
    request: Request,
    project_id: str,
    work_id: int,
    payload: StyleWorkAnalyzeRequest,
) -> ProjectEnvelope[StyleJobResponse]:
    if (
        payload.preset == "full"
        and request.app.state.settings.style_model_provider == "disabled"
    ):
        raise AnalyzerProviderUnavailableError()
    target = resolve_project_target(request, project_id)
    with open_project_services(target):
        pass
    service = StyleJobService(
        data_root=request.app.state.settings.data_root,
        notify=request.app.state.style_analysis_worker.notify,
    )
    job = service.enqueue(
        project_id,
        "analyze_reference_work",
        {"reference_work_id": work_id, **payload.model_dump(exclude_none=True)},
    )
    return envelope(project_id, _job_response(job))


@router.post(
    "/documents/{document_id}/lint",
    response_model=ProjectEnvelope[StyleJobResponse],
    status_code=202,
)
def lint_document(
    request: Request,
    project_id: str,
    document_id: int,
    payload: StyleLintRequest,
) -> ProjectEnvelope[StyleJobResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target):
        pass
    service = StyleJobService(
        data_root=request.app.state.settings.data_root,
        notify=request.app.state.style_analysis_worker.notify,
    )
    job = service.enqueue(
        project_id,
        "run_lint",
        {"document_id": document_id, **payload.model_dump(exclude_none=True)},
    )
    return envelope(project_id, _job_response(job))


@router.get("/lint-runs")
def list_lint_runs(
    request: Request,
    project_id: str,
    document_id: int | None = Query(None, gt=0),
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        runs = services.style_analysis.list_lint_runs(document_id)
    return envelope(project_id, list(runs))


@router.get("/lint-runs/{lint_run_id}")
def get_lint_run(
    request: Request, project_id: str, lint_run_id: int
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        run = services.style_analysis.get_lint_run(lint_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, run)


@router.get("/lint-runs/{lint_run_id}/findings")
def list_lint_findings(
    request: Request, project_id: str, lint_run_id: int
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_lint_run(lint_run_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        findings = services.style_analysis.list_lint_findings(lint_run_id)
    return envelope(project_id, list(findings))


@router.post("/findings/{finding_id}/review")
def review_lint_finding(
    request: Request,
    project_id: str,
    finding_id: int,
    payload: StyleFindingReviewRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        finding = services.style_analysis.review_lint_finding(
            finding_id, payload.status, payload.note
        )
    return envelope(project_id, finding)


@router.get(
    "/jobs/{job_id}",
    response_model=ProjectEnvelope[StyleJobResponse],
)
def get_style_job(
    request: Request, project_id: str, job_id: int
) -> ProjectEnvelope[StyleJobResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target):
        pass
    job = StyleJobService(data_root=request.app.state.settings.data_root).get(
        project_id, job_id
    )
    if job is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, _job_response(job))


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=ProjectEnvelope[StyleJobResponse],
)
def cancel_style_job(
    request: Request, project_id: str, job_id: int
) -> ProjectEnvelope[StyleJobResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target):
        pass
    job = StyleJobService(data_root=request.app.state.settings.data_root).cancel(
        project_id, job_id
    )
    return envelope(project_id, _job_response(job))


@router.post(
    "/jobs/{job_id}/retry",
    response_model=ProjectEnvelope[StyleJobResponse],
    status_code=202,
)
def retry_style_job(
    request: Request, project_id: str, job_id: int
) -> ProjectEnvelope[StyleJobResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target):
        pass
    service = StyleJobService(
        data_root=request.app.state.settings.data_root,
        notify=request.app.state.style_analysis_worker.notify,
    )
    return envelope(project_id, _job_response(service.retry(project_id, job_id)))


@router.get("/analysis-runs")
def list_analysis_runs_canonical(
    request: Request,
    project_id: str,
    document_id: int | None = Query(None, gt=0),
) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        runs = services.style_analysis.list_analysis_runs(document_id)
    return envelope(project_id, list(runs))


@router.get("/analysis-runs/{run_id}")
def get_analysis_run(
    request: Request, project_id: str, run_id: int
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        run = services.style_analysis.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, run)


@router.get("/analysis-runs/{run_id}/outputs")
def list_analysis_run_outputs(
    request: Request, project_id: str, run_id: int
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_analysis_run(run_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        outputs = services.style_analysis.list_run_outputs(run_id)
    return envelope(project_id, list(outputs))


@router.get("/analysis-runs/{run_id}/measurements")
def list_analysis_run_measurements(
    request: Request, project_id: str, run_id: int
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_analysis_run(run_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        measurements = services.style_analysis.list_run_measurements(run_id)
    return envelope(project_id, list(measurements))


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


def _episode_response(
    record: ReferenceEpisodeRecord,
    analysis_status: dict[str, object] | None = None,
) -> ReferenceEpisodeResponse:
    return ReferenceEpisodeResponse(
        reference_episode_id=record.id,
        reference_work_id=record.reference_work_id,
        title=record.title,
        order_index=record.order_index,
        style_document_id=record.style_document_id,
        current_text_revision_id=record.current_text_revision_id,
        current_structure_revision_id=record.current_structure_revision_id,
        current_structure_kind=record.current_structure_kind,
        analysis_status=analysis_status
        or {
            "basic": {"state": "not_analyzed", "reasons": []},
            "semantic": {"state": "not_analyzed", "reasons": []},
        },
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


router.include_router(corpus_profile_router)
router.include_router(documents_router)
router.include_router(review_router)
