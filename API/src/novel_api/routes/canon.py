from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope, raise_version_conflict
from novel_api.schemas.canon import CanonStatusSet
from novel_api.schemas.common import ProjectEnvelope
from novel_api.service_container import ServiceContainer, open_project_services

router = APIRouter(prefix="/api/v1/projects/{project_id}/canon", tags=["canon"])


def _phase1_entity(services: ServiceContainer, entity_type: str, entity_id: int) -> Any:
    readers = {
        "world_fact": services.world_fact.get,
        "timeline_event": services.timeline.get_event,
        "character": services.character.get,
        "relationship": services.relationship.get,
    }
    reader = readers.get(entity_type)
    return None if reader is None else reader(entity_id)


@router.post("/status", response_model=ProjectEnvelope[Any])
def set_canon_status(
    request: Request, project_id: str, body: CanonStatusSet
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            decision = services.canon.set_canon_status(
                body.entity_type,
                body.entity_id,
                body.target_status,
                body.expected_version,
                body.reason,
            )
        except VersionConflictError:
            current = _phase1_entity(services, body.entity_type, body.entity_id)
            if current is None:
                raise
            raise_version_conflict(
                entity_type=body.entity_type,
                entity_id=body.entity_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, decision)


@router.get("/decisions/search", response_model=ProjectEnvelope[Any])
def search_canon_decisions(
    request: Request,
    project_id: str,
    query: str,
    limit: int = Query(default=20),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.canon.search_decisions(query, limit))


@router.get("/decisions/{decision_id}", response_model=ProjectEnvelope[Any])
def get_canon_decision(
    request: Request, project_id: str, decision_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, services.canon.get_decision(decision_id))
