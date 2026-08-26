from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast

from novel_mcp.errors import (
    CanonEntityNotFoundError,
    NarrativeNotFoundError,
    OrderConflictError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
)
from novel_mcp.repositories.narrative_repository import (
    ChapterRecord,
    EpisodeRecord,
    NarrativeRepository,
    SceneRecord,
)
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.canon_service import CanonService

CANON_STATUSES = frozenset(("idea", "draft", "canon", "deprecated"))
PRODUCTION_STATUSES = frozenset(
    ("planned", "outlined", "drafting", "revising", "final")
)
RecordT = TypeVar("RecordT", ChapterRecord, EpisodeRecord, SceneRecord)


class NarrativeService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._repository = NarrativeRepository(connection)
        self._work_repository = WorkRepository(connection)
        self._canon_service = CanonService(connection)

    def create_chapter(
        self,
        title: str,
        summary: str = "",
        purpose: str = "",
        production_status: str = "planned",
        canon_status: str = "draft",
    ) -> ChapterRecord:
        fields = self._hierarchy_fields(
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
        )
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            chapter_id = self._repository.create_chapter(work_id=work_id, fields=fields)
            record = self._repository.get_chapter(
                work_id=work_id, chapter_id=chapter_id
            )
            if record is None:
                raise sqlite3.IntegrityError("chapter creation failed")
            self._repository.commit()
            return record
        except Exception:
            self._repository.rollback()
            raise

    def create_episode(
        self,
        chapter_id: int,
        title: str,
        summary: str = "",
        purpose: str = "",
        foreshadowing_notes: Any = None,
        production_status: str = "planned",
        canon_status: str = "draft",
    ) -> EpisodeRecord:
        self.get_chapter(chapter_id)
        fields = self._hierarchy_fields(
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
        )
        fields["foreshadowing_notes_json"] = self._json_text(
            [] if foreshadowing_notes is None else foreshadowing_notes,
            "foreshadowing_notes",
        )
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            episode_id = self._repository.create_episode(
                work_id=work_id, chapter_id=chapter_id, fields=fields
            )
            record = self._repository.get_episode(
                work_id=work_id, episode_id=episode_id
            )
            if record is None:
                raise sqlite3.IntegrityError("episode creation failed")
            self._repository.commit()
            return record
        except Exception:
            self._repository.rollback()
            raise

    def create_scene(
        self,
        episode_id: int,
        title: str,
        summary: str = "",
        purpose: str = "",
        production_status: str = "planned",
        canon_status: str = "draft",
    ) -> SceneRecord:
        self.get_episode(episode_id)
        fields = self._hierarchy_fields(
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
        )
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            scene_id = self._repository.create_scene(
                work_id=work_id, episode_id=episode_id, fields=fields
            )
            record = self._repository.get_scene(work_id=work_id, scene_id=scene_id)
            if record is None:
                raise sqlite3.IntegrityError("scene creation failed")
            self._repository.commit()
            return record
        except Exception:
            self._repository.rollback()
            raise

    def get_chapter(self, chapter_id: int) -> ChapterRecord:
        record = self._repository.get_chapter(
            work_id=self._work_id(), chapter_id=chapter_id
        )
        if record is None:
            raise NarrativeNotFoundError()
        return record

    def get_episode(self, episode_id: int) -> EpisodeRecord:
        record = self._repository.get_episode(
            work_id=self._work_id(), episode_id=episode_id
        )
        if record is None:
            raise NarrativeNotFoundError()
        return record

    def get_scene(self, scene_id: int) -> SceneRecord:
        record = self._repository.get_scene(work_id=self._work_id(), scene_id=scene_id)
        if record is None:
            raise NarrativeNotFoundError()
        return record

    def list_chapters(self) -> tuple[ChapterRecord, ...]:
        return self._repository.list_chapters(work_id=self._work_id())

    def list_episodes(self, chapter_id: int) -> tuple[EpisodeRecord, ...]:
        self.get_chapter(chapter_id)
        return self._repository.list_episodes(
            work_id=self._work_id(), chapter_id=chapter_id
        )

    def list_scenes(self, episode_id: int) -> tuple[SceneRecord, ...]:
        self.get_episode(episode_id)
        return self._repository.list_scenes(
            work_id=self._work_id(), episode_id=episode_id
        )

    def reorder_chapter(
        self, chapter_id: int, target_position: int, expected_version: int
    ) -> tuple[ChapterRecord, ...]:
        return self._reorder(
            table="chapters",
            parent_column="work_id",
            parent_id=self._work_id(),
            entity_id=chapter_id,
            target_position=target_position,
            expected_version=expected_version,
            current_getter=self.get_chapter,
            sibling_getter=lambda _parent_id: self.list_chapters(),
        )

    def reorder_episode(
        self, episode_id: int, target_position: int, expected_version: int
    ) -> tuple[EpisodeRecord, ...]:
        current = self.get_episode(episode_id)
        return self._reorder(
            table="episodes",
            parent_column="chapter_id",
            parent_id=current.chapter_id,
            entity_id=episode_id,
            target_position=target_position,
            expected_version=expected_version,
            current_getter=self.get_episode,
            sibling_getter=self.list_episodes,
        )

    def reorder_scene(
        self, scene_id: int, target_position: int, expected_version: int
    ) -> tuple[SceneRecord, ...]:
        current = self.get_scene(scene_id)
        return self._reorder(
            table="scenes",
            parent_column="episode_id",
            parent_id=current.episode_id,
            entity_id=scene_id,
            target_position=target_position,
            expected_version=expected_version,
            current_getter=self.get_scene,
            sibling_getter=self.list_scenes,
        )

    def _reorder(
        self,
        *,
        table: str,
        parent_column: str,
        parent_id: int,
        entity_id: int,
        target_position: int,
        expected_version: int,
        current_getter: Callable[[int], RecordT],
        sibling_getter: Callable[[int], tuple[RecordT, ...]],
    ) -> tuple[RecordT, ...]:
        self._validate_version(expected_version)
        if isinstance(target_position, bool) or not isinstance(target_position, int):
            raise OrderConflictError("target_position must be an integer")
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            current = current_getter(entity_id)
            if current.version != expected_version:
                raise VersionConflictError("VERSION_CONFLICT")
            siblings = sibling_getter(parent_id)
            if target_position < 1 or target_position > len(siblings):
                raise OrderConflictError("target_position is outside the sibling range")
            old_index = current.position - 1
            new_index = target_position - 1
            if old_index == new_index:
                self._repository.commit()
                return siblings
            ordered = list(siblings)
            moved = ordered.pop(old_index)
            ordered.insert(new_index, moved)
            changed_start = min(old_index, new_index)
            changed_end = max(old_index, new_index)
            affected = tuple(row.id for row in ordered[changed_start : changed_end + 1])
            final_positions = {
                row.id: index + 1
                for index, row in enumerate(ordered)
                if row.id in affected
            }
            self._repository.reorder_positions(
                table=table,
                parent_column=parent_column,
                work_id=work_id,
                parent_id=parent_id,
                final_positions=final_positions,
                affected_ids=affected,
            )
            result = sibling_getter(parent_id)
            self._repository.commit()
            return result
        except Exception:
            self._repository.rollback()
            raise

    def update_chapter(
        self,
        chapter_id: int,
        expected_version: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        production_status: str | None = None,
        canon_status: str | None = None,
        reason: str | None = None,
    ) -> ChapterRecord:
        self._validate_version(expected_version)
        self.get_chapter(chapter_id)
        fields = self._update_fields(
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
        )
        return self._update(
            "chapters",
            "chapter",
            chapter_id,
            expected_version,
            fields,
            self.get_chapter,
            reason=reason,
        )

    def update_episode(
        self,
        episode_id: int,
        expected_version: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        foreshadowing_notes: Any = None,
        production_status: str | None = None,
        canon_status: str | None = None,
        reason: str | None = None,
    ) -> EpisodeRecord:
        self._validate_version(expected_version)
        self.get_episode(episode_id)
        fields = self._update_fields(
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
        )
        if foreshadowing_notes is not None:
            fields["foreshadowing_notes_json"] = self._json_text(
                foreshadowing_notes, "foreshadowing_notes"
            )
        return self._update(
            "episodes",
            "episode",
            episode_id,
            expected_version,
            fields,
            self.get_episode,
            reason=reason,
        )

    def update_scene(
        self,
        scene_id: int,
        expected_version: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        purpose: str | None = None,
        production_status: str | None = None,
        canon_status: str | None = None,
        reason: str | None = None,
    ) -> SceneRecord:
        self._validate_version(expected_version)
        self.get_scene(scene_id)
        fields = self._update_fields(
            title=title,
            summary=summary,
            purpose=purpose,
            production_status=production_status,
            canon_status=canon_status,
        )
        return self._update(
            "scenes",
            "scene",
            scene_id,
            expected_version,
            fields,
            self.get_scene,
            reason=reason,
        )

    def _update(
        self,
        table: str,
        entity_type: str,
        entity_id: int,
        expected_version: int,
        fields: Mapping[str, object],
        getter: Callable[[int], RecordT],
        *,
        reason: str | None,
    ) -> RecordT:
        normalized = dict(fields)
        target_status = cast(str | None, normalized.pop("canon_status", None))
        if not normalized and target_status is None:
            raise ValidationError("at least one field is required")
        try:
            self._canon_service.update_content(
                entity_type,
                entity_id,
                normalized,
                expected_version=expected_version,
                reason=reason,
                target_status=target_status,
            )
        except CanonEntityNotFoundError as exc:
            raise NarrativeNotFoundError() from exc
        return getter(entity_id)

    def _hierarchy_fields(self, **fields: str) -> dict[str, object]:
        title = self._required_text(fields.pop("title"), "title")
        result: dict[str, object] = {"title": title}
        for name in ("summary", "purpose"):
            result[name] = self._text(fields.pop(name), name)
        self._validate_statuses(fields["production_status"], fields["canon_status"])
        result.update(fields)
        return result

    def _update_fields(self, **fields: str | None) -> dict[str, object]:
        result: dict[str, object] = {}
        for name in ("title", "summary", "purpose"):
            value = fields.pop(name)
            if value is not None:
                result[name] = (
                    self._required_text(value, name)
                    if name == "title"
                    else self._text(value, name)
                )
        for name in ("production_status", "canon_status"):
            value = fields.pop(name)
            if value is not None:
                self._validate_status(name, value)
                result[name] = value
        return result

    def _validate_statuses(self, production_status: str, canon_status: str) -> None:
        self._validate_status("production_status", production_status)
        self._validate_status("canon_status", canon_status)

    def _validate_status(self, field_name: str, value: str) -> None:
        choices = (
            PRODUCTION_STATUSES if field_name == "production_status" else CANON_STATUSES
        )
        if value not in choices:
            raise ValidationError(f"unsupported {field_name}", field=field_name)

    def _validate_version(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError(
                "expected_version must be at least 1", field="expected_version"
            )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _required_text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return value.strip()

    def _text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field=field_name)
        return value.strip()

    def _json_text(self, value: object, field_name: str) -> str:
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"{field_name} must be valid JSON", field=field_name
            ) from exc
