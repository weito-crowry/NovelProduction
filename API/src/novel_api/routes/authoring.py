from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.errors import ApiVersionConflictError, build_conflict_details
from novel_api.routes._phase1 import envelope
from novel_api.schemas.authoring import DraftSave
from novel_api.schemas.common import ProjectEnvelope
from novel_api.service_container import open_project_services

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["authoring"])


@router.get(
    "/episodes/{episode_id}/outline",
    response_model=ProjectEnvelope[Any],
)
def get_episode_outline(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.outline.get_episode_outline(episode_id))


@router.get(
    "/episodes/{episode_id}/context",
    response_model=ProjectEnvelope[Any],
)
def get_episode_context(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.context.build_episode_context(episode_id))


@router.get(
    "/episodes/{episode_id}/draft",
    response_model=ProjectEnvelope[Any],
)
def get_episode_draft(
    request: Request,
    project_id: str,
    episode_id: int,
    revision: int | None = Query(default=None, ge=1),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.draft.get_draft(episode_id, revision))


@router.post(
    "/episodes/{episode_id}/drafts",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def save_episode_draft(
    request: Request,
    project_id: str,
    episode_id: int,
    body: DraftSave,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            saved = services.draft.save_draft(
                episode_id,
                body.body,
                expected_parent_draft_id=body.expected_parent_draft_id,
                source_agent=body.source_agent,
                change_summary=body.change_summary,
            )
        except VersionConflictError:
            latest = services.draft.get_draft(episode_id)
            if latest is None or body.expected_parent_draft_id is None:
                raise
            raise ApiVersionConflictError(
                build_conflict_details(
                    entity_type="draft",
                    entity_id=episode_id,
                    expected_version=body.expected_parent_draft_id,
                    current_version=latest.id,
                    current_resource=latest,
                )
            ) from None
        return envelope(project_id, saved)


@router.get(
    "/episodes/{episode_id}/drafts",
    response_model=ProjectEnvelope[Any],
)
def list_episode_drafts(
    request: Request,
    project_id: str,
    episode_id: int,
    limit: int = Query(default=20, ge=1, le=100),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.draft.history(episode_id, limit))
