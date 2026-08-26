from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from novel_mcp.errors import (
    NarrativeNotFoundError,
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
            "chapters", chapter_id, expected_version, fields, self.get_chapter
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
            "episodes", episode_id, expected_version, fields, self.get_episode
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
            "scenes", scene_id, expected_version, fields, self.get_scene
        )

    def _update(
        self,
        table: str,
        entity_id: int,
        expected_version: int,
        fields: Mapping[str, object],
        getter: Callable[[int], RecordT],
    ) -> RecordT:
        if not fields:
            raise ValidationError("at least one field is required")
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            updated = self._repository.update(
                table=table,
                entity_id=entity_id,
                work_id=work_id,
                expected_version=expected_version,
                fields=fields,
            )
            if not updated:
                raise VersionConflictError("VERSION_CONFLICT")
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
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
