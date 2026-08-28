from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import compact_json, envelope, raise_version_conflict
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.work import WorkUpdate
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}/work", tags=["work"])


@router.get("", response_model=ProjectEnvelope[Any])
def get_work(request: Request, project_id: str) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.work.get())


@router.patch("", response_model=ProjectEnvelope[Any])
def update_work(
    request: Request, project_id: str, body: WorkUpdate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.work.update(
                body.working_title,
                body.expected_version,
                genre=body.genre,
                premise=body.premise,
                themes_json=(
                    compact_json(body.themes_json)
                    if body.themes_json is not None
                    else None
                ),
                description=body.description,
                production_status=body.production_status,
            )
        except VersionConflictError:
            current = services.work.get()
            raise_version_conflict(
                entity_type="work",
                entity_id=current.id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)
