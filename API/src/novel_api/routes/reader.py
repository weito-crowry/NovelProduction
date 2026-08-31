from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from novel_core.document import render_web_html
from novel_core.errors import NarrativeNotFoundError, WorkNotFoundError
from novel_core.repositories.narrative_repository import (
    ChapterRecord,
    EpisodeRecord,
)
from novel_core.repositories.work_repository import WorkRecord
from novel_core.services.draft_service import DraftSnapshot

from novel_api.dependencies import resolve_project_target
from novel_api.service_container import ServiceContainer, open_project_read_services

router = APIRouter(prefix="/read/projects", tags=["reader"])

_READER_CSS = """
:root {
  color-scheme: light;
  font-family: system-ui, -apple-system, BlinkMacSystemFont,
    "Hiragino Sans", "Yu Gothic", sans-serif;
}
body { background: #fff; color: #202124; margin: 0; }
.reader-page {
  box-sizing: border-box;
  margin: 0 auto;
  max-width: 48rem;
  padding: 1.5rem 1rem 3rem;
}
.reader-header { margin-bottom: 1.5rem; }
.reader-eyebrow { color: #5f6368; font-size: .9rem; margin: 0 0 .5rem; }
.reader-work-title { font-size: 1.35rem; margin: 0; }
.reader-chapter-title { color: #5f6368; margin: .5rem 0 0; }
h1 { font-size: clamp(1.6rem, 6vw, 2.2rem); line-height: 1.35; margin: .4rem 0 0; }
h2 { font-size: 1.25rem; line-height: 1.4; margin: 0; }
a { color: #1457b8; }
a, .reader-nav-disabled { min-height: 2.75rem; }
.reader-navigation {
  align-items: center;
  border-bottom: 1px solid #dadce0;
  border-top: 1px solid #dadce0;
  display: flex;
  flex-wrap: wrap;
  gap: .75rem;
  justify-content: space-between;
  margin: 1rem 0 1.5rem;
  padding: .75rem 0;
}
.reader-navigation a, .reader-nav-disabled {
  align-items: center;
  display: inline-flex;
  justify-content: center;
  padding: .4rem .25rem;
}
.reader-nav-disabled { color: #9aa0a6; }
.reader-position { color: #5f6368; font-size: .9rem; margin: .75rem 0 0; }
.chapter-section + .chapter-section { margin-top: 2rem; }
.episode-list { list-style: none; margin: .75rem 0 0; padding: 0; }
.episode-list li {
  align-items: center;
  border-bottom: 1px solid #edf0f2;
  display: flex;
  gap: .75rem;
  justify-content: space-between;
  padding: .8rem 0;
}
.episode-list a { display: block; flex: 1; padding: .3rem 0; }
.episode-unavailable { color: #6b7280; font-size: .9rem; white-space: nowrap; }
#novel-body { font-size: 1.08rem; line-height: 2; overflow-wrap: anywhere; }
#novel-body img { height: auto; max-width: 100%; }
"""


@dataclass(frozen=True, slots=True)
class _ReaderEpisode:
    episode: EpisodeRecord
    chapter_title: str
    draft: DraftSnapshot | None


@dataclass(frozen=True, slots=True)
class _ReaderChapter:
    chapter: ChapterRecord
    episodes: tuple[_ReaderEpisode, ...]


@dataclass(frozen=True, slots=True)
class _ReaderCatalog:
    work: WorkRecord
    chapters: tuple[_ReaderChapter, ...]

    @property
    def episodes(self) -> tuple[_ReaderEpisode, ...]:
        return tuple(
            episode for chapter in self.chapters for episode in chapter.episodes
        )


@router.get("/{project_id}/", response_class=HTMLResponse)
def read_project(request: Request, project_id: str) -> HTMLResponse:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        catalog = _load_catalog(services)
    return _html_response(_render_toc(project_id, catalog))


@router.get("/{project_id}/episodes/{episode_id}/", response_class=HTMLResponse)
def read_episode(request: Request, project_id: str, episode_id: int) -> HTMLResponse:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        try:
            services.narrative.get_episode(episode_id)
        except NarrativeNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Not Found") from exc

        catalog = _load_catalog(services)

    current = next(
        (item for item in catalog.episodes if item.episode.id == episode_id),
        None,
    )
    if current is None or current.draft is None:
        raise HTTPException(status_code=404, detail="Not Found")

    ordered = tuple(item for item in catalog.episodes if item.draft is not None)
    current_index = ordered.index(current)
    previous = ordered[current_index - 1] if current_index > 0 else None
    following = ordered[current_index + 1] if current_index + 1 < len(ordered) else None
    return _html_response(
        _render_episode(
            project_id,
            catalog.work,
            current,
            current_index + 1,
            len(ordered),
            previous,
            following,
        )
    )


def _load_catalog(services: ServiceContainer) -> _ReaderCatalog:
    try:
        work = services.work.get()
    except WorkNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Not Found") from exc

    chapters: list[_ReaderChapter] = []
    for chapter in services.narrative.list_chapters():
        episodes = tuple(
            _ReaderEpisode(
                episode=episode,
                chapter_title=chapter.title,
                draft=services.draft.get_draft(episode.id),
            )
            for episode in services.narrative.list_episodes(chapter.id)
        )
        chapters.append(_ReaderChapter(chapter=chapter, episodes=episodes))
    return _ReaderCatalog(work=work, chapters=tuple(chapters))


def _render_toc(project_id: str, catalog: _ReaderCatalog) -> str:
    sections: list[str] = []
    for chapter in catalog.chapters:
        episode_items = "".join(
            _render_toc_episode(project_id, item) for item in chapter.episodes
        )
        sections.append(
            f'<section class="chapter-section" '
            f'aria-labelledby="chapter-{chapter.chapter.id}">'
            f'<h2 id="chapter-{chapter.chapter.id}">'
            f"{_escape(chapter.chapter.title)}</h2>"
            f'<ul class="episode-list">{episode_items}</ul>'
            "</section>"
        )

    return _render_document(
        f"{catalog.work.working_title} - 目次",
        f'<header class="reader-header"><p class="reader-eyebrow">読書ビュー</p>'
        f'<h1 class="reader-work-title">'
        f"{_escape(catalog.work.working_title)}</h1></header>" + "".join(sections),
    )


def _render_toc_episode(project_id: str, item: _ReaderEpisode) -> str:
    title = _escape(item.episode.title)
    if item.draft is None:
        return (
            f"<li><span>{title}</span>"
            '<span class="episode-unavailable">本文未作成</span></li>'
        )
    href = _episode_url(project_id, item.episode.id)
    return f'<li><a href="{href}">{title}</a></li>'


def _render_episode(
    project_id: str,
    work: WorkRecord,
    current: _ReaderEpisode,
    position: int,
    total: int,
    previous: _ReaderEpisode | None,
    following: _ReaderEpisode | None,
) -> str:
    assert current.draft is not None
    body = render_web_html(current.draft.document, include_notes=False)
    header = (
        '<header class="reader-header">'
        f'<p class="reader-eyebrow">{_escape(work.working_title)}</p>'
        f'<p class="reader-chapter-title">{_escape(current.chapter_title)}</p>'
        f"<h1>{_escape(current.episode.title)}</h1>"
        f'<p class="reader-position">{position} / {total}</p>'
        "</header>"
    )
    navigation = _render_navigation(project_id, previous, following)
    return _render_document(
        f"{work.working_title} - {current.episode.title}",
        header + navigation + f'<article id="novel-body">{body}</article>' + navigation,
    )


def _render_navigation(
    project_id: str,
    previous: _ReaderEpisode | None,
    following: _ReaderEpisode | None,
) -> str:
    previous_link = (
        f'<a rel="prev" href="'
        f'{_episode_url(project_id, previous.episode.id)}">前の話</a>'
        if previous is not None
        else '<span class="reader-nav-disabled">前の話</span>'
    )
    following_link = (
        f'<a rel="next" href="'
        f'{_episode_url(project_id, following.episode.id)}">次の話</a>'
        if following is not None
        else '<span class="reader-nav-disabled">次の話</span>'
    )
    contents = f'<a rel="contents" href="{_project_url(project_id)}">目次</a>'
    return (
        '<nav class="reader-navigation" aria-label="Episode navigation">'
        + previous_link
        + contents
        + following_link
        + "</nav>"
    )


def _render_document(title: str, content: str) -> str:
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_escape(title)}</title><style>{_READER_CSS}</style>"
        f'</head><body><main class="reader-page">{content}</main></body></html>'
    )


def _html_response(content: str) -> HTMLResponse:
    return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})


def _project_url(project_id: str) -> str:
    return f"/read/projects/{quote(project_id, safe='')}/"


def _episode_url(project_id: str, episode_id: int) -> str:
    return f"{_project_url(project_id)}episodes/{episode_id}/"


def _escape(value: str) -> str:
    return escape(value, quote=True)
