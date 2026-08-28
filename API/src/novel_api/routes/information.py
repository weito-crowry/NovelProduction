from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope, raise_version_conflict
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.information import (
    CharacterKnowledgeSet,
    InformationCreate,
    InformationUpdate,
    ReaderDisclosureSet,
)
from novel_api.service_container import open_project_services

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["information"])


@router.post(
    "/information",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def create_information(
    request: Request, project_id: str, body: InformationCreate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.information.create_information(
            body.statement,
            truth_status=body.truth_status,
            authoring_guard=body.authoring_guard,
            notes_json=body.notes_json,
            canon_status=body.canon_status,
            importance=body.importance,
        )
        return envelope(project_id, created)


@router.get("/information/search", response_model=ProjectEnvelope[Any])
def search_information(
    request: Request,
    project_id: str,
    query: str,
    limit: int = Query(default=20),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        results = services.information.search_information(query, limit)
        return envelope(project_id, results)


@router.get("/information/{information_item_id}", response_model=ProjectEnvelope[Any])
def get_information(
    request: Request, project_id: str, information_item_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        item = services.information.get_information(information_item_id)
        return envelope(project_id, item)


@router.patch("/information/{information_item_id}", response_model=ProjectEnvelope[Any])
def update_information(
    request: Request,
    project_id: str,
    information_item_id: int,
    body: InformationUpdate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.information.update_information(
                information_item_id,
                body.expected_version,
                statement=body.statement,
                truth_status=body.truth_status,
                authoring_guard=body.authoring_guard,
                notes_json=body.notes_json,
                importance=body.importance,
                canon_status=body.canon_status,
                reason=body.reason,
            )
        except VersionConflictError:
            current = services.information.get_information(information_item_id)
            raise_version_conflict(
                entity_type="information_item",
                entity_id=information_item_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@router.put(
    "/information/{information_item_id}/reader-disclosure",
    response_model=ProjectEnvelope[Any],
)
def set_reader_disclosure(
    request: Request,
    project_id: str,
    information_item_id: int,
    body: ReaderDisclosureSet,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        disclosure = services.disclosure.set_reader_disclosure(
            information_item_id,
            body.episode_id,
            expected_version=body.expected_version,
        )
        return envelope(project_id, disclosure)


@router.put(
    "/characters/{character_id}/knowledge/{information_item_id}",
    response_model=ProjectEnvelope[Any],
)
def set_character_knowledge(
    request: Request,
    project_id: str,
    character_id: int,
    information_item_id: int,
    body: CharacterKnowledgeSet,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        event = services.knowledge.set_character_knowledge(
            character_id,
            information_item_id,
            body.episode_id,
            body.knowledge_state,
            body.note,
            expected_version=body.expected_version,
        )
        return envelope(project_id, event)


@router.get(
    "/characters/{character_id}/knowledge",
    response_model=ProjectEnvelope[Any],
)
def get_character_knowledge(
    request: Request,
    project_id: str,
    character_id: int,
    episode_id: int = Query(),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        knowledge = services.knowledge.get_character_knowledge(character_id, episode_id)
        return envelope(project_id, knowledge)
