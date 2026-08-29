from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope, raise_version_conflict
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.timeline import (
    TimelineEventCreate,
    TimelineEventUpdate,
    TimelineMove,
    TimelineRelationCreate,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}/timeline", tags=["timeline"])


def _participants(body: TimelineEventCreate | TimelineEventUpdate) -> Any:
    if body.participants is None:
        return None
    return tuple((item.character_id, item.role) for item in body.participants)


@router.post(
    "/events", response_model=ProjectEnvelope[Any], status_code=status.HTTP_201_CREATED
)
def create_timeline_event(
    request: Request, project_id: str, body: TimelineEventCreate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.timeline.create_event(
            body.event_date,
            body.title,
            participants=_participants(body),
            event_key=body.event_key,
            time_start=body.time_start,
            time_end=body.time_end,
            date_precision=body.date_precision,
            date_display=body.date_display,
            description=body.description,
            category=body.category,
            location_world_fact_id=body.location_world_fact_id,
            cause_summary=body.cause_summary,
            consequence_summary=body.consequence_summary,
            importance=body.importance,
        )
        return envelope(project_id, created)


@router.get("/events", response_model=ProjectEnvelope[Any])
def list_timeline_events(
    request: Request,
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.timeline.list_events(limit, offset))


@router.get("/events/search", response_model=ProjectEnvelope[Any])
def search_timeline_events(
    request: Request,
    project_id: str,
    query: str,
    limit: int = Query(default=20),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.timeline.search_events(query, limit))


@router.get("/events/{event_id}", response_model=ProjectEnvelope[Any])
def get_timeline_event(
    request: Request, project_id: str, event_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.timeline.get_event(event_id))


@router.patch("/events/{event_id}", response_model=ProjectEnvelope[Any])
def update_timeline_event(
    request: Request,
    project_id: str,
    event_id: int,
    body: TimelineEventUpdate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.timeline.update_event(
                event_id,
                body.expected_version,
                title=body.title,
                new_date=body.new_date,
                participants=_participants(body),
                reason=body.reason,
                time_start=body.time_start,
                time_end=body.time_end,
                date_precision=body.date_precision,
                date_display=body.date_display,
                description=body.description,
                category=body.category,
                location_world_fact_id=body.location_world_fact_id,
                cause_summary=body.cause_summary,
                consequence_summary=body.consequence_summary,
                importance=body.importance,
            )
        except VersionConflictError:
            current = services.timeline.get_event(event_id)
            raise_version_conflict(
                entity_type="timeline_event",
                entity_id=event_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@router.get("/range", response_model=ProjectEnvelope[Any])
def range_timeline_events(
    request: Request,
    project_id: str,
    start: str,
    end: str,
    limit: int = Query(default=20),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.timeline.range_events(start, end, limit))


@router.post("/events/{event_id}/move", response_model=ProjectEnvelope[Any])
def move_timeline_event(
    request: Request, project_id: str, event_id: int, body: TimelineMove
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.timeline.move_event(
                event_id, body.expected_version, body.new_date, body.reason
            )
        except VersionConflictError:
            current = services.timeline.get_event(event_id)
            raise_version_conflict(
                entity_type="timeline_event",
                entity_id=event_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@router.post(
    "/relations",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def create_timeline_relation(
    request: Request, project_id: str, body: TimelineRelationCreate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.timeline.create_relation(
            body.source_id, body.target_id, body.relation_type
        )
        return envelope(project_id, created)


@router.get("/relations", response_model=ProjectEnvelope[Any])
def list_timeline_relations(
    request: Request,
    project_id: str,
    event_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(
            project_id, services.timeline.list_relations(event_id, limit, offset)
        )
