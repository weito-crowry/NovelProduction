from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from pydantic import Field

from novel_mcp.tool_support import call_service

Registrar = Callable[..., None]
Id = Annotated[int, Field(ge=1)]
OptionalId = Annotated[int | None, Field(ge=1)]
OptionalRevision = Annotated[int | None, Field(ge=1)]
HistoryLimit = Annotated[int, Field(ge=1, le=100)]
SourceAgent = Annotated[str | None, Field(min_length=1, max_length=120)]
ChangeSummary = Annotated[str, Field(max_length=1000)]


def run_phase3_acceptance(*args: Any, **kwargs: Any) -> Any:
    from novel_mcp.phase3_acceptance import run_phase3_acceptance as _run

    return _run(*args, **kwargs)


def register_phase3_tools(services: Any, register: Registrar) -> None:
    async def episode_outline_get(episode_id: Id) -> dict[str, Any]:
        return await call_service(services.outline.get_episode_outline, episode_id)

    async def episode_context(episode_id: Id) -> dict[str, Any]:
        return await call_service(services.context.build_episode_context, episode_id)

    async def episode_draft_get(
        episode_id: Id, revision: OptionalRevision = None
    ) -> dict[str, Any]:
        return await call_service(services.drafts.get_draft, episode_id, revision)

    async def episode_draft_save(
        episode_id: Id,
        body: Annotated[str, Field(min_length=1)],
        expected_parent_draft_id: OptionalId = None,
        source_agent: SourceAgent = None,
        change_summary: ChangeSummary = "",
    ) -> dict[str, Any]:
        return await call_service(
            services.drafts.save_draft,
            episode_id,
            body,
            expected_parent_draft_id,
            source_agent,
            change_summary,
        )

    async def episode_draft_history(
        episode_id: Id, limit: HistoryLimit = 20
    ) -> dict[str, Any]:
        return await call_service(services.drafts.history, episode_id, limit)

    register(
        "episode_outline_get",
        episode_outline_get,
        read_only=True,
        destructive=False,
    )
    register("episode_context", episode_context, read_only=True, destructive=False)
    register(
        "episode_draft_get",
        episode_draft_get,
        read_only=True,
        destructive=False,
    )
    register(
        "episode_draft_save",
        episode_draft_save,
        read_only=False,
        destructive=False,
    )
    register(
        "episode_draft_history",
        episode_draft_history,
        read_only=True,
        destructive=False,
    )
