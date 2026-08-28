from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status
from novel_core.errors import VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope, raise_version_conflict
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.narrative import (
    ChapterCreate,
    ChapterUpdate,
    CharacterStateSet,
    EpisodeCreate,
    EpisodeReferenceAdd,
    EpisodeUpdate,
    Reorder,
    SceneCreate,
    SceneUpdate,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["narrative"])


@router.post(
    "/chapters",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def create_chapter(
    request: Request, project_id: str, body: ChapterCreate
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.narrative.create_chapter(
            body.title,
            body.summary,
            body.purpose,
            body.production_status,
            body.canon_status,
        )
        return envelope(project_id, created)


@router.get("/chapters", response_model=ProjectEnvelope[Any])
def list_chapters(request: Request, project_id: str) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.narrative.list_chapters())


@router.patch("/chapters/{chapter_id}", response_model=ProjectEnvelope[Any])
def update_chapter(
    request: Request,
    project_id: str,
    chapter_id: int,
    body: ChapterUpdate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.narrative.update_chapter(
                chapter_id,
                body.expected_version,
                title=body.title,
                summary=body.summary,
                purpose=body.purpose,
                production_status=body.production_status,
                canon_status=body.canon_status,
                reason=body.reason,
            )
        except VersionConflictError:
            current = services.narrative.get_chapter(chapter_id)
            raise_version_conflict(
                entity_type="chapter",
                entity_id=chapter_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@router.post("/chapters/{chapter_id}/reorder", response_model=ProjectEnvelope[Any])
def reorder_chapter(
    request: Request,
    project_id: str,
    chapter_id: int,
    body: Reorder,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            ordered = services.narrative.reorder_chapter(
                chapter_id, body.target_position, body.expected_version
            )
        except VersionConflictError:
            current = services.narrative.get_chapter(chapter_id)
            raise_version_conflict(
                entity_type="chapter",
                entity_id=chapter_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, ordered)


@router.post(
    "/chapters/{chapter_id}/episodes",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def create_episode(
    request: Request,
    project_id: str,
    chapter_id: int,
    body: EpisodeCreate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.narrative.create_episode(
            chapter_id,
            body.title,
            body.summary,
            body.purpose,
            body.foreshadowing_notes,
            body.production_status,
            body.canon_status,
        )
        return envelope(project_id, created)


@router.get("/chapters/{chapter_id}/episodes", response_model=ProjectEnvelope[Any])
def list_episodes(
    request: Request, project_id: str, chapter_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.narrative.list_episodes(chapter_id))


@router.get("/episodes/{episode_id}", response_model=ProjectEnvelope[Any])
def get_episode(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.narrative.get_episode(episode_id))


@router.patch("/episodes/{episode_id}", response_model=ProjectEnvelope[Any])
def update_episode(
    request: Request,
    project_id: str,
    episode_id: int,
    body: EpisodeUpdate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.narrative.update_episode(
                episode_id,
                body.expected_version,
                title=body.title,
                summary=body.summary,
                purpose=body.purpose,
                foreshadowing_notes=body.foreshadowing_notes,
                production_status=body.production_status,
                canon_status=body.canon_status,
                reason=body.reason,
            )
        except VersionConflictError:
            current = services.narrative.get_episode(episode_id)
            raise_version_conflict(
                entity_type="episode",
                entity_id=episode_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@router.post("/episodes/{episode_id}/reorder", response_model=ProjectEnvelope[Any])
def reorder_episode(
    request: Request,
    project_id: str,
    episode_id: int,
    body: Reorder,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            ordered = services.narrative.reorder_episode(
                episode_id, body.target_position, body.expected_version
            )
        except VersionConflictError:
            current = services.narrative.get_episode(episode_id)
            raise_version_conflict(
                entity_type="episode",
                entity_id=episode_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, ordered)


@router.post(
    "/episodes/{episode_id}/scenes",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def create_scene(
    request: Request,
    project_id: str,
    episode_id: int,
    body: SceneCreate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.narrative.create_scene(
            episode_id,
            body.title,
            body.summary,
            body.purpose,
            body.production_status,
            body.canon_status,
        )
        return envelope(project_id, created)


@router.get("/episodes/{episode_id}/scenes", response_model=ProjectEnvelope[Any])
def list_scenes(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.narrative.list_scenes(episode_id))


@router.get("/scenes/{scene_id}", response_model=ProjectEnvelope[Any])
def get_scene(request: Request, project_id: str, scene_id: int) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.narrative.get_scene(scene_id))


@router.patch("/scenes/{scene_id}", response_model=ProjectEnvelope[Any])
def update_scene(
    request: Request,
    project_id: str,
    scene_id: int,
    body: SceneUpdate,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            updated = services.narrative.update_scene(
                scene_id,
                body.expected_version,
                title=body.title,
                summary=body.summary,
                purpose=body.purpose,
                production_status=body.production_status,
                canon_status=body.canon_status,
                reason=body.reason,
            )
        except VersionConflictError:
            current = services.narrative.get_scene(scene_id)
            raise_version_conflict(
                entity_type="scene",
                entity_id=scene_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, updated)


@router.post("/scenes/{scene_id}/reorder", response_model=ProjectEnvelope[Any])
def reorder_scene(
    request: Request,
    project_id: str,
    scene_id: int,
    body: Reorder,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            ordered = services.narrative.reorder_scene(
                scene_id, body.target_position, body.expected_version
            )
        except VersionConflictError:
            current = services.narrative.get_scene(scene_id)
            raise_version_conflict(
                entity_type="scene",
                entity_id=scene_id,
                expected_version=body.expected_version,
                current_resource=current,
            )
        return envelope(project_id, ordered)


@router.post(
    "/episodes/{episode_id}/references",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def add_episode_reference(
    request: Request,
    project_id: str,
    episode_id: int,
    body: EpisodeReferenceAdd,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        created = services.episode_reference.add(
            episode_id,
            body.reference_type,
            body.target_id,
            role=body.role,
        )
        return envelope(project_id, created)


@router.delete(
    "/episodes/{episode_id}/references/{reference_type}/{target_id}",
    response_model=ProjectEnvelope[Any],
)
def remove_episode_reference(
    request: Request,
    project_id: str,
    episode_id: int,
    reference_type: str,
    target_id: int,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        removed = services.episode_reference.remove(
            episode_id, reference_type, target_id
        )
        return envelope(project_id, removed)


@router.get("/episodes/{episode_id}/references", response_model=ProjectEnvelope[Any])
def list_episode_references(
    request: Request,
    project_id: str,
    episode_id: int,
    reference_type: str | None = Query(default=None),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        references = services.episode_reference.list(
            episode_id, reference_type=reference_type
        )
        return envelope(project_id, references)


@router.put(
    "/characters/{character_id}/states/{episode_id}",
    response_model=ProjectEnvelope[Any],
)
def set_character_state(
    request: Request,
    project_id: str,
    character_id: int,
    episode_id: int,
    body: CharacterStateSet,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        state_record = services.character_state.set_state(
            character_id,
            episode_id,
            physical_state=body.physical_state,
            emotional_state=body.emotional_state,
            beliefs_json=body.beliefs_json,
            location_world_fact_id=body.location_world_fact_id,
            state_json=body.state_json,
            expected_version=body.expected_version,
        )
        return envelope(project_id, state_record)


@router.get(
    "/characters/{character_id}/states/{episode_id}",
    response_model=ProjectEnvelope[Any],
)
def get_character_state(
    request: Request,
    project_id: str,
    character_id: int,
    episode_id: int,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        state_record = services.character_state.get_effective_state(
            character_id, episode_id
        )
        return envelope(project_id, state_record)


@router.get("/characters/{character_id}/states", response_model=ProjectEnvelope[Any])
def get_character_state_history(
    request: Request, project_id: str, character_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.character_state.history(character_id))
