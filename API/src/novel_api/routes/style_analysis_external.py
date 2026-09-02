from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.style_analysis_external import (
    ExternalAnalysisCancelRequest,
    ExternalAnalysisStartRequest,
    ExternalAnalysisSubmitRequest,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)

router = APIRouter()
_STATUS_VALUES = Literal["active", "succeeded", "partial", "failed", "cancelled"]


@router.post("/external-sessions", status_code=201)
def external_analysis_start(
    request: Request,
    project_id: str,
    payload: ExternalAnalysisStartRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        snapshot = services.external_analysis.start(
            target=payload.target.model_dump(),
            executor_model_id=payload.executor_model_id,
            rebuild_structure=payload.rebuild_structure,
        )
    return envelope(project_id, snapshot)


@router.get("/external-sessions")
def external_analysis_list(
    request: Request,
    project_id: str,
    status: Annotated[_STATUS_VALUES | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        sessions = services.external_analysis.list(status=status, limit=limit)
    return envelope(project_id, sessions)


@router.get("/external-sessions/{session_id}")
def external_analysis_status(
    request: Request, project_id: str, session_id: int
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        snapshot = services.external_analysis.get(session_id)
    return envelope(project_id, snapshot)


@router.post("/external-sessions/{session_id}/tasks/{task_id}/submit")
def external_analysis_submit(
    request: Request,
    project_id: str,
    session_id: int,
    task_id: int,
    payload: ExternalAnalysisSubmitRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        snapshot = services.external_analysis.submit(
            session_id=session_id,
            task_id=task_id,
            expected_task_version=payload.expected_task_version,
            executor_model_id=payload.executor_model_id,
            response=payload.response,
        )
    return envelope(project_id, snapshot)


@router.post("/external-sessions/{session_id}/cancel")
def external_analysis_cancel(
    request: Request,
    project_id: str,
    session_id: int,
    payload: ExternalAnalysisCancelRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        snapshot = services.external_analysis.cancel(
            session_id=session_id,
            expected_session_version=payload.expected_session_version,
        )
    return envelope(project_id, snapshot)
