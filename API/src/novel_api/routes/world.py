from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import compact_json, envelope, raise_version_conflict
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.world import WorldFactCreate, WorldFactUpdate
from novel_api.service_container import open_project_services

router = APIRouter(prefix="/api/v1/projects/{project_id}/world-facts", tags=["world"])


@router.post(
    "", response_model=ProjectEnvelope[Any], status_code=status.HTTP_201_CREATED
)
def create_world_fact(
    request: Request, project_id: str, body: WorldFactCreate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.world_fact.create(
            body.statement,
            body.valid_from,
            body.valid_to,
            topic_key=body.topic_key,
            category=body.category,
            title=body.title,
            details_json=compact_json(body.details_json),
            importance=body.importance,
        )
        return envelope(project_id, created)


@router.get("/search", response_model=ProjectEnvelope[Any])
def search_world_facts(
    request: Request,
    project_id: str,
    query: str,
    limit: int = Query(default=20),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.world_fact.search(query, limit))


@router.get("/{fact_id}", response_model=ProjectEnvelope[Any])
def get_world_fact(
    request: Request, project_id: str, fact_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.world_fact.get(fact_id))


@router.patch("/{fact_id}", response_model=ProjectEnvelope[Any])
def update_world_fact(
    request: Request, project_id: str, fact_id: int, body: WorldFactUpdate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.world_fact.update(
                fact_id,
                body.statement,
                body.expected_version,
                body.reason,
                topic_key=body.topic_key,
                category=body.category,
                title=body.title,
                details_json=(
                    compact_json(body.details_json)
                    if body.details_json is not None
                    else None
                ),
                valid_from=body.valid_from,
                valid_to=body.valid_to,
                importance=body.importance,
            )
        except VersionConflictError:
            current = services.world_fact.get(fact_id)
            raise_version_conflict(
                entity_type="world_fact",
                entity_id=fact_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)
