from __future__ import annotations

from fastapi import APIRouter, Request

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.views import (
    DashboardView,
    EpisodeView,
    OutlineChapterView,
    OutlineEpisodeView,
    OutlineView,
)
from novel_api.service_container import ServiceContainer, open_project_services

router = APIRouter(prefix="/api/v1/projects/{project_id}/views", tags=["views"])


def _build_outline(services: ServiceContainer) -> OutlineView:
    chapters: list[OutlineChapterView] = []
    for chapter in services.narrative.list_chapters():
        episodes: list[OutlineEpisodeView] = []
        for episode in services.narrative.list_episodes(chapter.id):
            episodes.append(
                OutlineEpisodeView(
                    episode=episode,
                    scenes=list(services.narrative.list_scenes(episode.id)),
                )
            )
        chapters.append(OutlineChapterView(chapter=chapter, episodes=episodes))
    return OutlineView(chapters=chapters)


@router.get("/outline", response_model=ProjectEnvelope[OutlineView])
def get_outline_view(request: Request, project_id: str) -> ProjectEnvelope[OutlineView]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(project_id, _build_outline(services))


@router.get("/dashboard", response_model=ProjectEnvelope[DashboardView])
def get_dashboard_view(
    request: Request, project_id: str
) -> ProjectEnvelope[DashboardView]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        outline = _build_outline(services)
        return envelope(
            project_id,
            DashboardView(
                work=services.work.get(),
                chapter_count=len(outline.chapters),
                episode_count=sum(
                    len(chapter.episodes) for chapter in outline.chapters
                ),
                scene_count=sum(
                    len(episode.scenes)
                    for chapter in outline.chapters
                    for episode in chapter.episodes
                ),
            ),
        )


@router.get("/episodes/{episode_id}", response_model=ProjectEnvelope[EpisodeView])
def get_episode_view(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[EpisodeView]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        return envelope(
            project_id,
            EpisodeView(
                episode=services.narrative.get_episode(episode_id),
                scenes=list(services.narrative.list_scenes(episode_id)),
                episode_references=list(services.episode_reference.list(episode_id)),
                outline=services.outline.get_episode_outline(episode_id),
                context=services.context.build_episode_context(episode_id),
                latest_draft=services.draft.get_draft(episode_id),
                recent_draft_history=list(services.draft.history(episode_id, limit=20)),
            ),
        )
