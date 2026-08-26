from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.relationship_service import RelationshipService
from novel_mcp.services.search_service import SearchService
from novel_mcp.services.timeline_service import TimelineService
from novel_mcp.services.work_service import WorkService
from novel_mcp.services.world_fact_service import WorldFactService
from novel_mcp.tool_errors import error_payload, success

PHASE1_TOOL_NAMES = frozenset(
    {
        "work_get",
        "work_update",
        "world_fact_create",
        "world_fact_update",
        "world_fact_get",
        "world_fact_search",
        "timeline_event_create",
        "timeline_event_update",
        "timeline_event_get",
        "timeline_event_search",
        "timeline_range",
        "timeline_move",
        "timeline_relation_create",
        "character_create",
        "character_update",
        "character_get",
        "character_search",
        "relationship_create",
        "relationship_update",
        "relationship_search",
        "canon_status_set",
        "canon_decision_get",
        "canon_decision_search",
    }
)


class Phase1MCPServer(MCPServer):
    def tool_names(self) -> frozenset[str]:
        return frozenset(tool.name for tool in self._tool_manager.list_tools())


Handler = Callable[..., Awaitable[dict[str, Any]]]


def create_server(config: DatabaseConfig) -> Phase1MCPServer:
    connection = open_database(config)
    services = {
        "work": WorkService(connection),
        "world": WorldFactService(connection),
        "timeline": TimelineService(connection),
        "character": CharacterService(connection),
        "relationship": RelationshipService(connection),
        "canon": CanonService(connection),
        "search": SearchService(connection),
    }
    server = Phase1MCPServer("novel-production", version="0.1.0")

    def register(name: str, handler: Handler, *, read_only: bool) -> None:
        annotations = ToolAnnotations(
            readOnlyHint=read_only,
            destructiveHint=False if read_only else None,
            openWorldHint=False,
        )
        server.add_tool(
            handler, name=name, annotations=annotations, structured_output=True
        )

    async def work_get() -> dict[str, Any]:
        return await _call(services["work"].get)

    async def work_update(title: str, expected_version: int) -> dict[str, Any]:
        return await _call(services["work"].update, title, expected_version)

    async def world_fact_create(
        statement: str, valid_from: str | None = None, valid_to: str | None = None
    ) -> dict[str, Any]:
        return await _call(services["world"].create, statement, valid_from, valid_to)

    async def world_fact_update(
        fact_id: int, statement: str, expected_version: int
    ) -> dict[str, Any]:
        return await _call(
            services["world"].update, fact_id, statement, expected_version
        )

    async def world_fact_get(fact_id: int) -> dict[str, Any]:
        return await _call(services["world"].get, fact_id)

    async def world_fact_search(query: str, limit: int = 20) -> dict[str, Any]:
        return await _call(services["world"].search, query, limit)

    async def timeline_event_create(
        event_date: str, title: str, participants: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        pairs = tuple((item["label"], item["role"]) for item in (participants or []))
        return await _call(
            services["timeline"].create_event, event_date, title, participants=pairs
        )

    async def timeline_event_update(
        event_id: int,
        expected_version: int,
        title: str | None = None,
        new_date: str | None = None,
        participants: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        pairs = (
            None
            if participants is None
            else tuple((item["label"], item["role"]) for item in participants)
        )
        return await _call(
            services["timeline"].update_event,
            event_id,
            expected_version,
            title=title,
            new_date=new_date,
            participants=pairs,
        )

    async def timeline_event_get(event_id: int) -> dict[str, Any]:
        return await _call(services["timeline"].get_event, event_id)

    async def timeline_event_search(query: str, limit: int = 20) -> dict[str, Any]:
        return await _call(services["timeline"].search_events, query, limit)

    async def timeline_range(start: str, end: str, limit: int = 20) -> dict[str, Any]:
        return await _call(services["timeline"].range_events, start, end, limit)

    async def timeline_move(
        event_id: int, expected_version: int, new_date: str
    ) -> dict[str, Any]:
        return await _call(
            services["timeline"].move_event, event_id, expected_version, new_date
        )

    async def timeline_relation_create(
        source_id: int, target_id: int, relation_type: str
    ) -> dict[str, Any]:
        return await _call(
            services["timeline"].create_relation, source_id, target_id, relation_type
        )

    async def character_create(name: str, profile: str | None = None) -> dict[str, Any]:
        return await _call(services["character"].create, name, profile)

    async def character_update(
        character_id: int,
        expected_version: int,
        name: str | None = None,
        profile: str | None = None,
    ) -> dict[str, Any]:
        return await _call(
            services["character"].update,
            character_id,
            expected_version,
            name=name,
            profile=profile,
        )

    async def character_get(character_id: int) -> dict[str, Any]:
        return await _call(services["character"].get, character_id)

    async def character_search(query: str, limit: int = 20) -> dict[str, Any]:
        return await _call(services["character"].search, query, limit)

    async def relationship_create(
        source_character_id: int, target_character_id: int, relation_type: str
    ) -> dict[str, Any]:
        return await _call(
            services["relationship"].create,
            source_character_id,
            target_character_id,
            relation_type,
        )

    async def relationship_update(
        relationship_id: int, expected_version: int, relation_type: str
    ) -> dict[str, Any]:
        return await _call(
            services["relationship"].update,
            relationship_id,
            expected_version,
            relation_type,
        )

    async def relationship_search(
        character_id: int | None = None, limit: int = 20
    ) -> dict[str, Any]:
        return await _call(services["relationship"].search, character_id, limit)

    async def canon_status_set(
        entity_type: str, entity_id: int, target_status: str, reason: str | None = None
    ) -> dict[str, Any]:
        return await _call(
            services["canon"].set_canon_status,
            entity_type,
            entity_id,
            target_status,
            reason,
        )

    async def canon_decision_get(decision_id: int) -> dict[str, Any]:
        return await _call(services["canon"].get_decision, decision_id)

    async def canon_decision_search(query: str, limit: int = 20) -> dict[str, Any]:
        return await _call(services["canon"].search_decisions, query, limit)

    for name, handler, read_only in (
        ("work_get", work_get, True),
        ("work_update", work_update, False),
        ("world_fact_create", world_fact_create, False),
        ("world_fact_update", world_fact_update, False),
        ("world_fact_get", world_fact_get, True),
        ("world_fact_search", world_fact_search, True),
        ("timeline_event_create", timeline_event_create, False),
        ("timeline_event_update", timeline_event_update, False),
        ("timeline_event_get", timeline_event_get, True),
        ("timeline_event_search", timeline_event_search, True),
        ("timeline_range", timeline_range, True),
        ("timeline_move", timeline_move, False),
        ("timeline_relation_create", timeline_relation_create, False),
        ("character_create", character_create, False),
        ("character_update", character_update, False),
        ("character_get", character_get, True),
        ("character_search", character_search, True),
        ("relationship_create", relationship_create, False),
        ("relationship_update", relationship_update, False),
        ("relationship_search", relationship_search, True),
        ("canon_status_set", canon_status_set, False),
        ("canon_decision_get", canon_decision_get, True),
        ("canon_decision_search", canon_decision_search, True),
    ):
        register(name, handler, read_only=read_only)
    return server


async def _call(
    operation: Callable[..., Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    try:
        return success(operation(*args, **kwargs))
    except Exception as exc:
        return error_payload(exc)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--migration-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    server = create_server(DatabaseConfig(args.db, args.migration_dir))
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
