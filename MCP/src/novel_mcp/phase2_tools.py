from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import Field

from novel_mcp.tool_support import call_service

Registrar = Callable[..., None]
Limit = Annotated[int, Field(ge=0, le=100)]
Version = Annotated[int, Field(ge=1)]
OptionalVersion = Annotated[int | None, Field(ge=1)]
Position = Annotated[int, Field(ge=1)]
Id = Annotated[int, Field(ge=1)]
CanonStatus = Literal["idea", "draft", "canon", "deprecated"]
ProductionStatus = Literal["planned", "outlined", "drafting", "revising", "final"]
TruthStatus = Literal["true", "false", "uncertain", "subjective"]
KnowledgeState = Literal[
    "suspects", "believes", "knows", "confirmed", "doubts", "rejected"
]
ReferenceType = Literal["character", "world_fact", "timeline_event", "information"]


def register_phase2_tools(services: Any, register: Registrar) -> None:
    async def chapter_create(
        title: Annotated[str, Field(min_length=1)],
        summary: str = "",
        purpose: str = "",
        production_status: ProductionStatus = "planned",
        canon_status: CanonStatus = "draft",
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.create_chapter,
            title,
            summary,
            purpose,
            production_status,
            canon_status,
        )

    async def chapter_update(
        chapter_id: Id,
        expected_version: Version,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        production_status: ProductionStatus | None = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.update_chapter,
            chapter_id,
            expected_version,
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
            reason=reason,
        )

    async def chapter_reorder(
        chapter_id: Id, target_position: Position, expected_version: Version
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.reorder_chapter,
            chapter_id,
            target_position,
            expected_version,
        )

    async def chapter_list() -> dict[str, Any]:
        return await call_service(services.narrative.list_chapters)

    async def episode_create(
        chapter_id: Id,
        title: Annotated[str, Field(min_length=1)],
        summary: str = "",
        purpose: str = "",
        foreshadowing_notes: Any = None,
        production_status: ProductionStatus = "planned",
        canon_status: CanonStatus = "draft",
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.create_episode,
            chapter_id,
            title,
            summary,
            purpose,
            foreshadowing_notes,
            production_status,
            canon_status,
        )

    async def episode_update(
        episode_id: Id,
        expected_version: Version,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        foreshadowing_notes: Any = None,
        production_status: ProductionStatus | None = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.update_episode,
            episode_id,
            expected_version,
            title=title,
            summary=summary,
            purpose=purpose,
            foreshadowing_notes=foreshadowing_notes,
            production_status=production_status,
            canon_status=canon_status,
            reason=reason,
        )

    async def episode_get(episode_id: Id) -> dict[str, Any]:
        return await call_service(services.narrative.get_episode, episode_id)

    async def episode_reorder(
        episode_id: Id, target_position: Position, expected_version: Version
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.reorder_episode,
            episode_id,
            target_position,
            expected_version,
        )

    async def episode_list(chapter_id: Id) -> dict[str, Any]:
        return await call_service(services.narrative.list_episodes, chapter_id)

    async def scene_create(
        episode_id: Id,
        title: Annotated[str, Field(min_length=1)],
        summary: str = "",
        purpose: str = "",
        production_status: ProductionStatus = "planned",
        canon_status: CanonStatus = "draft",
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.create_scene,
            episode_id,
            title,
            summary,
            purpose,
            production_status,
            canon_status,
        )

    async def scene_update(
        scene_id: Id,
        expected_version: Version,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        production_status: ProductionStatus | None = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.update_scene,
            scene_id,
            expected_version,
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
            reason=reason,
        )

    async def scene_get(scene_id: Id) -> dict[str, Any]:
        return await call_service(services.narrative.get_scene, scene_id)

    async def scene_reorder(
        scene_id: Id, target_position: Position, expected_version: Version
    ) -> dict[str, Any]:
        return await call_service(
            services.narrative.reorder_scene,
            scene_id,
            target_position,
            expected_version,
        )

    async def scene_list(episode_id: Id) -> dict[str, Any]:
        return await call_service(services.narrative.list_scenes, episode_id)

    async def episode_reference_add(
        episode_id: Id,
        reference_type: ReferenceType,
        target_id: Id,
        role: Annotated[str, Field(min_length=1, max_length=120)] = "participant",
    ) -> dict[str, Any]:
        return await call_service(
            services.references.add,
            episode_id,
            reference_type,
            target_id,
            role=role,
        )

    async def episode_reference_remove(
        episode_id: Id, reference_type: ReferenceType, target_id: Id
    ) -> dict[str, Any]:
        return await call_service(
            services.references.remove, episode_id, reference_type, target_id
        )

    async def episode_reference_list(
        episode_id: Id, reference_type: ReferenceType | None = None
    ) -> dict[str, Any]:
        return await call_service(
            services.references.list, episode_id, reference_type=reference_type
        )

    async def character_state_set(
        character_id: Id,
        episode_id: Id,
        physical_state: str | None = None,
        emotional_state: str | None = None,
        beliefs_json: Any = None,
        location_world_fact_id: Id | None = None,
        state_json: Any = None,
        expected_version: OptionalVersion = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.state.set_state,
            character_id,
            episode_id,
            physical_state=physical_state,
            emotional_state=emotional_state,
            beliefs_json=beliefs_json,
            location_world_fact_id=location_world_fact_id,
            state_json=state_json,
            expected_version=expected_version,
        )

    async def character_state_get(character_id: Id, episode_id: Id) -> dict[str, Any]:
        return await call_service(
            services.state.get_effective_state, character_id, episode_id
        )

    async def character_state_history(character_id: Id) -> dict[str, Any]:
        return await call_service(services.state.history, character_id)

    async def information_create(
        statement: Annotated[str, Field(min_length=1)],
        truth_status: TruthStatus = "uncertain",
        authoring_guard: str = "",
        notes_json: Any = None,
        canon_status: CanonStatus = "draft",
        importance: Annotated[int, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        return await call_service(
            services.information.create_information,
            statement,
            truth_status=truth_status,
            authoring_guard=authoring_guard,
            notes_json=notes_json,
            canon_status=canon_status,
            importance=importance,
        )

    async def information_update(
        information_item_id: Id,
        expected_version: Version,
        statement: str | None = None,
        truth_status: TruthStatus | None = None,
        authoring_guard: str | None = None,
        notes_json: Any = None,
        importance: Annotated[int | None, Field(ge=0)] = None,
        canon_status: CanonStatus | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.information.update_information,
            information_item_id,
            expected_version,
            statement=statement,
            truth_status=truth_status,
            authoring_guard=authoring_guard,
            notes_json=notes_json,
            importance=importance,
            canon_status=canon_status,
            reason=reason,
        )

    async def information_get(information_item_id: Id) -> dict[str, Any]:
        return await call_service(
            services.information.get_information, information_item_id
        )

    async def information_search(query: str, limit: Limit = 20) -> dict[str, Any]:
        return await call_service(services.information.search_information, query, limit)

    async def reader_disclosure_set(
        information_item_id: Id,
        episode_id: Id,
        expected_version: OptionalVersion = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.disclosure.set_reader_disclosure,
            information_item_id,
            episode_id,
            expected_version=expected_version,
        )

    async def character_knowledge_set(
        character_id: Id,
        information_item_id: Id,
        episode_id: Id,
        knowledge_state: KnowledgeState,
        note: str = "",
        expected_version: OptionalVersion = None,
    ) -> dict[str, Any]:
        return await call_service(
            services.knowledge.set_character_knowledge,
            character_id,
            information_item_id,
            episode_id,
            knowledge_state,
            note,
            expected_version=expected_version,
        )

    async def character_knowledge_get(
        character_id: Id, episode_id: Id
    ) -> dict[str, Any]:
        return await call_service(
            services.knowledge.get_character_knowledge, character_id, episode_id
        )

    registrations = (
        ("chapter_create", chapter_create, False, False),
        ("chapter_update", chapter_update, False, True),
        ("chapter_reorder", chapter_reorder, False, True),
        ("chapter_list", chapter_list, True, False),
        ("episode_create", episode_create, False, False),
        ("episode_update", episode_update, False, True),
        ("episode_get", episode_get, True, False),
        ("episode_reorder", episode_reorder, False, True),
        ("episode_list", episode_list, True, False),
        ("scene_create", scene_create, False, False),
        ("scene_update", scene_update, False, True),
        ("scene_get", scene_get, True, False),
        ("scene_reorder", scene_reorder, False, True),
        ("scene_list", scene_list, True, False),
        ("episode_reference_add", episode_reference_add, False, False),
        ("episode_reference_remove", episode_reference_remove, False, True),
        ("episode_reference_list", episode_reference_list, True, False),
        ("character_state_set", character_state_set, False, True),
        ("character_state_get", character_state_get, True, False),
        ("character_state_history", character_state_history, True, False),
        ("information_create", information_create, False, False),
        ("information_update", information_update, False, True),
        ("information_get", information_get, True, False),
        ("information_search", information_search, True, False),
        ("reader_disclosure_set", reader_disclosure_set, False, True),
        ("character_knowledge_set", character_knowledge_set, False, True),
        ("character_knowledge_get", character_knowledge_get, True, False),
    )
    for name, handler, read_only, destructive in registrations:
        register(name, handler, read_only=read_only, destructive=destructive)
