from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class OutlineEpisodeView(BaseModel):
    episode: Any
    scenes: list[Any]


class OutlineChapterView(BaseModel):
    chapter: Any
    episodes: list[OutlineEpisodeView]


class OutlineView(BaseModel):
    chapters: list[OutlineChapterView]


class DashboardView(BaseModel):
    work: Any
    chapter_count: int
    episode_count: int
    scene_count: int


class EpisodeView(BaseModel):
    episode: Any
    scenes: list[Any]
    episode_references: list[Any]
    outline: Any
    context: Any
    latest_draft: Any | None
    recent_draft_history: list[Any]
