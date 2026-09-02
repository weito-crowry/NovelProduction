from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from novel_core.config import DatabaseConfig
from novel_core.database import (
    default_migration_dir,
    open_database,
    open_database_readonly,
)
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

from novel_api.style_analysis.catalog_service import StyleAnalysisCatalogService
from novel_api.style_analysis.external_service import ExternalAnalysisService


@dataclass(frozen=True, slots=True)
class ProjectDescriptor:
    project_dir: Path
    story_db: Path


@dataclass(frozen=True, slots=True)
class ProjectTarget:
    project_id: str
    descriptor: ProjectDescriptor


@dataclass(frozen=True, slots=True)
class ServiceContainer:
    work: WorkService
    world_fact: WorldFactService
    timeline: TimelineService
    character: CharacterService
    relationship: RelationshipService
    canon: CanonService
    search: SearchService
    narrative: NarrativeService
    character_state: CharacterStateService
    information: InformationService
    disclosure: DisclosureService
    knowledge: KnowledgeService
    episode_reference: EpisodeReferenceService
    draft: DraftService
    outline: OutlineService
    context: ContextService
    style_analysis: StyleAnalysisCatalogService
    external_analysis: ExternalAnalysisService


def _build_service_container(connection: sqlite3.Connection) -> ServiceContainer:
    style_analysis = StyleAnalysisCatalogService(connection)
    return ServiceContainer(
        work=WorkService(connection),
        world_fact=WorldFactService(connection),
        timeline=TimelineService(connection),
        character=CharacterService(connection),
        relationship=RelationshipService(connection),
        canon=CanonService(connection),
        search=SearchService(connection),
        narrative=NarrativeService(connection),
        character_state=CharacterStateService(connection),
        information=InformationService(connection),
        disclosure=DisclosureService(connection),
        knowledge=KnowledgeService(connection),
        episode_reference=EpisodeReferenceService(connection),
        draft=DraftService(connection),
        outline=OutlineService(connection),
        context=ContextService(connection),
        style_analysis=style_analysis,
        external_analysis=ExternalAnalysisService(
            connection, capture_project_draft=style_analysis.capture_project_draft
        ),
    )


@contextmanager
def open_project_services(target: ProjectTarget) -> Iterator[ServiceContainer]:
    connection = open_database(
        DatabaseConfig(
            db_path=target.descriptor.story_db,
            migration_dir=default_migration_dir(),
        )
    )
    try:
        yield _build_service_container(connection)
    finally:
        connection.close()


@contextmanager
def open_project_read_services(target: ProjectTarget) -> Iterator[ServiceContainer]:
    connection = open_database_readonly(
        DatabaseConfig(
            db_path=target.descriptor.story_db,
            migration_dir=default_migration_dir(),
        )
    )
    try:
        yield _build_service_container(connection)
    finally:
        connection.close()
