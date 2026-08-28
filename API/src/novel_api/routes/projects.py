from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from novel_api.project_registry import (
    ProjectConflictError,
    ProjectNotFoundError,
    ProjectRegistry,
)
from novel_api.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectStatusRequest,
    ProjectSummary,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _registry(request: Request) -> ProjectRegistry:
    return ProjectRegistry(request.app.state.settings.data_root)


def _translate_project_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="PROJECT_NOT_FOUND")
    if isinstance(exc, ProjectConflictError):
        return HTTPException(status_code=409, detail="PROJECT_CONFLICT")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("", response_model=ProjectListResponse)
def list_projects(
    request: Request, include_archived: bool = False
) -> ProjectListResponse:
    return ProjectListResponse(
        projects=_registry(request).list(include_archived=include_archived)
    )


@router.post("", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_project(request: Request, body: ProjectCreateRequest) -> ProjectSummary:
    try:
        return _registry(request).create(body.working_title, body.project_id)
    except (ProjectConflictError, ValueError) as exc:
        raise _translate_project_error(exc) from exc


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(request: Request, project_id: str) -> ProjectSummary:
    try:
        return _registry(request).get(project_id)
    except (ProjectNotFoundError, ValueError) as exc:
        raise _translate_project_error(exc) from exc


@router.patch("/{project_id}", response_model=ProjectSummary)
def set_project_status(
    request: Request, project_id: str, body: ProjectStatusRequest
) -> ProjectSummary:
    try:
        return _registry(request).set_status(project_id, body.status)
    except (ProjectNotFoundError, ValueError) as exc:
        raise _translate_project_error(exc) from exc
