from __future__ import annotations

import argparse
import asyncio
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.services.canon_service import CanonService
from novel_core.services.character_service import CharacterService
from novel_core.services.character_state_service import CharacterStateService
from novel_core.services.context_service import ContextService
from novel_core.services.disclosure_service import DisclosureService
from novel_core.services.draft_service import DraftService
from novel_core.services.episode_reference_service import EpisodeReferenceService
from novel_core.services.information_service import InformationService
from novel_core.services.knowledge_service import KnowledgeService
from novel_core.services.narrative_service import NarrativeService
from novel_core.services.outline_service import OutlineService
from novel_core.services.relationship_service import RelationshipService
from novel_core.services.search_service import SearchService
from novel_core.services.timeline_service import TimelineService
from novel_core.services.work_service import WorkService
from novel_core.services.world_fact_service import WorldFactService

from novel_mcp.phase1_tools import register_phase1_tools
from novel_mcp.phase2_tool_descriptions import PHASE2_TOOL_DESCRIPTIONS
from novel_mcp.phase2_tools import register_phase2_tools
from novel_mcp.phase3_tool_descriptions import PHASE3_TOOL_DESCRIPTIONS
from novel_mcp.phase3_tools import register_phase3_tools
from novel_mcp.tool_descriptions import TOOL_DESCRIPTIONS
from novel_mcp.tool_support import Handler

PHASE1_TOOL_NAMES = frozenset(TOOL_DESCRIPTIONS)
PHASE2_TOOL_NAMES = frozenset(PHASE2_TOOL_DESCRIPTIONS)
PHASE3_TOOL_NAMES = frozenset(PHASE3_TOOL_DESCRIPTIONS)
ALL_TOOL_NAMES = PHASE1_TOOL_NAMES | PHASE2_TOOL_NAMES | PHASE3_TOOL_NAMES


class Phase1MCPServer(MCPServer):
    def __init__(
        self, *args: Any, connection: sqlite3.Connection, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._connection = connection
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> Phase1MCPServer:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def tool_names(self) -> frozenset[str]:
        return frozenset(tool.name for tool in self._tool_manager.list_tools())

    @property
    def database(self) -> sqlite3.Connection:
        return self._connection


@dataclass(frozen=True, slots=True)
class ServiceContainer:
    work: WorkService
    world: WorldFactService
    timeline: TimelineService
    character: CharacterService
    relationship: RelationshipService
    canon: CanonService
    search: SearchService
    narrative: NarrativeService
    state: CharacterStateService
    information: InformationService
    disclosure: DisclosureService
    knowledge: KnowledgeService
    references: EpisodeReferenceService
    drafts: DraftService
    outline: OutlineService
    context: ContextService


Registrar = Callable[..., None]


def create_server(config: DatabaseConfig) -> Phase1MCPServer:
    connection = open_database(config)
    try:
        services = ServiceContainer(
            work=WorkService(connection),
            world=WorldFactService(connection),
            timeline=TimelineService(connection),
            character=CharacterService(connection),
            relationship=RelationshipService(connection),
            canon=CanonService(connection),
            search=SearchService(connection),
            narrative=NarrativeService(connection),
            state=CharacterStateService(connection),
            information=InformationService(connection),
            disclosure=DisclosureService(connection),
            knowledge=KnowledgeService(connection),
            references=EpisodeReferenceService(connection),
            drafts=DraftService(connection),
            outline=OutlineService(connection),
            context=ContextService(connection),
        )
        server = Phase1MCPServer(
            "novel-production", version="0.1.0", connection=connection
        )
    except Exception:
        connection.close()
        raise

    descriptions = {
        **TOOL_DESCRIPTIONS,
        **PHASE2_TOOL_DESCRIPTIONS,
        **PHASE3_TOOL_DESCRIPTIONS,
    }

    def register(
        name: str, handler: Handler, *, read_only: bool, destructive: bool
    ) -> None:
        server.add_tool(
            handler,
            name=name,
            description=descriptions[name],
            annotations=ToolAnnotations(
                read_only_hint=read_only,
                destructive_hint=destructive,
                open_world_hint=False,
            ),
            structured_output=True,
        )

    register_phase1_tools(services, register)
    register_phase2_tools(services, register)
    register_phase3_tools(services, register)
    return server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--migration-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    server = create_server(DatabaseConfig(args.db, args.migration_dir))
    try:
        asyncio.run(server.run_stdio_async())
    finally:
        server.close()


if __name__ == "__main__":
    main()
