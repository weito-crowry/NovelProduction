from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import compact_json, envelope, raise_version_conflict
from novel_api.schemas.characters import (
    CharacterCreate,
    CharacterUpdate,
    RelationshipCreate,
    RelationshipUpdate,
)
from novel_api.schemas.common import ProjectEnvelope
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)

characters_router = APIRouter(
    prefix="/api/v1/projects/{project_id}/characters", tags=["characters"]
)
relationships_router = APIRouter(
    prefix="/api/v1/projects/{project_id}/relationships", tags=["relationships"]
)


@characters_router.post(
    "", response_model=ProjectEnvelope[Any], status_code=status.HTTP_201_CREATED
)
def create_character(
    request: Request, project_id: str, body: CharacterCreate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.character.create(
            character_key=body.character_key,
            display_name=body.display_name,
            entity_type=body.entity_type,
            description=body.description,
            birth_date=body.birth_date,
            death_date=body.death_date,
            physical_description=body.physical_description,
            occupation=body.occupation,
            core_beliefs=body.core_beliefs,
            goals=body.goals,
            fears=body.fears,
            personality=body.personality,
            speech_style=body.speech_style,
            ai_attitude=body.ai_attitude,
            genetic_modification_attitude=body.genetic_modification_attitude,
            private_notes=body.private_notes,
            profile_json=compact_json(body.profile_json),
        )
        return envelope(project_id, created)


@characters_router.get("", response_model=ProjectEnvelope[Any])
def list_characters(
    request: Request,
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.character.list(limit, offset))


@characters_router.get("/search", response_model=ProjectEnvelope[Any])
def search_characters(
    request: Request,
    project_id: str,
    query: str,
    limit: int = Query(default=20),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.search.search_characters(query, limit))


@characters_router.get("/{character_id}", response_model=ProjectEnvelope[Any])
def get_character(
    request: Request, project_id: str, character_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.character.get(character_id))


@characters_router.patch("/{character_id}", response_model=ProjectEnvelope[Any])
def update_character(
    request: Request,
    project_id: str,
    character_id: int,
    body: CharacterUpdate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.character.update(
                character_id,
                body.expected_version,
                reason=body.reason,
                character_key=body.character_key,
                display_name=body.display_name,
                entity_type=body.entity_type,
                description=body.description,
                birth_date=body.birth_date,
                death_date=body.death_date,
                physical_description=body.physical_description,
                occupation=body.occupation,
                core_beliefs=body.core_beliefs,
                goals=body.goals,
                fears=body.fears,
                personality=body.personality,
                speech_style=body.speech_style,
                ai_attitude=body.ai_attitude,
                genetic_modification_attitude=body.genetic_modification_attitude,
                private_notes=body.private_notes,
                profile_json=(
                    compact_json(body.profile_json)
                    if body.profile_json is not None
                    else None
                ),
            )
        except VersionConflictError:
            current = services.character.get(character_id)
            raise_version_conflict(
                entity_type="character",
                entity_id=character_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@relationships_router.post(
    "", response_model=ProjectEnvelope[Any], status_code=status.HTTP_201_CREATED
)
def create_relationship(
    request: Request, project_id: str, body: RelationshipCreate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.relationship.create(
            body.source_character_id,
            body.target_character_id,
            body.relationship_type,
            body.description,
            valid_from_episode_id=body.valid_from_episode_id,
            valid_to_episode_id=body.valid_to_episode_id,
        )
        return envelope(project_id, created)


@relationships_router.patch("/{relationship_id}", response_model=ProjectEnvelope[Any])
def update_relationship(
    request: Request,
    project_id: str,
    relationship_id: int,
    body: RelationshipUpdate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.relationship.update(
                relationship_id,
                body.expected_version,
                body.relationship_type,
                body.reason,
                description=body.description,
                valid_from_episode_id=body.valid_from_episode_id,
                valid_to_episode_id=body.valid_to_episode_id,
                clear_valid_from=body.clear_valid_from,
                clear_valid_to=body.clear_valid_to,
            )
        except VersionConflictError:
            current = services.relationship.get(relationship_id)
            raise_version_conflict(
                entity_type="relationship",
                entity_id=relationship_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@relationships_router.get("", response_model=ProjectEnvelope[Any])
def search_relationships(
    request: Request,
    project_id: str,
    character_id: int | None = None,
    limit: int = Query(default=20),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.relationship.search(character_id, limit))
