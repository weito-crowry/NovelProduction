from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from novel_core.document import (
    NovelDocument,
    import_plain_text,
    parse_document_json,
    resolve_authoring,
    serialize_document_json,
)
from novel_core.errors import (
    DocumentSchemaError,
    DocumentStorageError,
    NarrativeNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_core.repositories.character_repository import CharacterRepository
from novel_core.repositories.draft_repository import (
    DraftMetadata,
    DraftRecord,
    DraftRepository,
)
from novel_core.repositories.narrative_repository import NarrativeRepository
from novel_core.repositories.work_repository import WorkRepository


@dataclass(frozen=True, slots=True)
class DraftSnapshot:
    """A stored draft record whose canonical JSON has crossed the parse boundary."""

    id: int
    work_id: int
    episode_id: int
    revision: int
    parent_draft_id: int | None
    document: NovelDocument
    source_agent: str | None
    change_summary: str
    created_at: str


@dataclass(frozen=True, slots=True)
class DraftSaveResult:
    """The compact response returned after a successful draft append."""

    id: int
    revision: int
    parent_draft_id: int | None
    id_map: dict[str, str]


class DraftService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = DraftRepository(connection)
        self._narrative_repository = NarrativeRepository(connection)
        self._character_repository = CharacterRepository(connection)
        self._work_repository = WorkRepository(connection)

    def save_draft(
        self,
        episode_id: int,
        *,
        plain_text: str | None = None,
        html: str | None = None,
        metadata_updates: Mapping[str, object] | None = None,
        restore_revision: int | None = None,
        expected_parent_draft_id: int | None = None,
        source_agent: str | None = None,
        change_summary: str = "",
    ) -> DraftSaveResult:
        self._validate_positive_int(episode_id, "episode_id")
        self._validate_optional_text(plain_text, "plain_text")
        self._validate_optional_text(html, "html")
        if metadata_updates is not None and not isinstance(metadata_updates, Mapping):
            raise ValidationError(
                "metadata_updates must be an object", field="metadata_updates"
            )
        self._validate_optional_positive_int(restore_revision, "restore_revision")
        self._validate_optional_positive_int(
            expected_parent_draft_id, "expected_parent_draft_id"
        )
        self._validate_source_agent(source_agent)
        self._validate_change_summary(change_summary)
        self._validate_combination(plain_text, html, metadata_updates, restore_revision)
        work_id = self._validate_episode(episode_id)

        self._repository.begin_write()
        try:
            latest = self._repository.latest(work_id=work_id, episode_id=episode_id)
            if latest is None:
                revision, parent_draft_id, document, id_map = self._resolve_initial(
                    plain_text=plain_text,
                    html=html,
                    metadata_updates=metadata_updates,
                    restore_revision=restore_revision,
                    expected_parent_draft_id=expected_parent_draft_id,
                )
                parent_document = None
            else:
                if expected_parent_draft_id is None:
                    raise ValidationError(
                        "expected_parent_draft_id is required",
                        field="expected_parent_draft_id",
                    )
                if expected_parent_draft_id != latest.id:
                    raise VersionConflictError("VERSION_CONFLICT")
                parent_snapshot = self._snapshot_from_record(latest)
                revision = latest.revision + 1
                parent_draft_id = latest.id
                parent_document = parent_snapshot.document
                document, id_map = self._resolve_existing(
                    work_id=work_id,
                    episode_id=episode_id,
                    parent_document=parent_document,
                    plain_text=plain_text,
                    html=html,
                    metadata_updates=metadata_updates,
                    restore_revision=restore_revision,
                )

            if restore_revision is None:
                self._validate_live_references(
                    work_id=work_id,
                    episode_id=episode_id,
                    parent=parent_document,
                    document=document,
                )
            document_json = serialize_document_json(document)
            draft_id = self._repository.insert(
                work_id=work_id,
                episode_id=episode_id,
                revision=revision,
                parent_draft_id=parent_draft_id,
                document_json=document_json,
                source_agent=source_agent,
                change_summary=change_summary,
            )
            inserted = self._repository.get(
                work_id=work_id, episode_id=episode_id, revision=revision
            )
            if inserted is None:
                raise sqlite3.IntegrityError("draft retrieval failed")
            inserted_snapshot = self._snapshot_from_record(inserted)
            if (
                inserted_snapshot.id != draft_id
                or inserted_snapshot.work_id != work_id
                or inserted_snapshot.episode_id != episode_id
                or inserted_snapshot.revision != revision
                or inserted_snapshot.parent_draft_id != parent_draft_id
            ):
                raise sqlite3.IntegrityError("inserted draft identity mismatch")
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise

        return DraftSaveResult(
            id=draft_id,
            revision=revision,
            parent_draft_id=parent_draft_id,
            id_map=id_map,
        )

    def get_draft(
        self, episode_id: int, revision: int | None = None
    ) -> DraftSnapshot | None:
        self._validate_positive_int(episode_id, "episode_id")
        if revision is not None:
            self._validate_positive_int(revision, "revision")
        work_id = self._validate_episode(episode_id)
        record = self._repository.get(
            work_id=work_id, episode_id=episode_id, revision=revision
        )
        return None if record is None else self._snapshot_from_record(record)

    def history(self, episode_id: int, limit: int = 20) -> tuple[DraftMetadata, ...]:
        self._validate_positive_int(episode_id, "episode_id")
        self._validate_limit(limit)
        work_id = self._validate_episode(episode_id)
        return self._repository.history(
            work_id=work_id, episode_id=episode_id, limit=limit
        )

    def latest_metadata(self) -> tuple[DraftMetadata, ...]:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return self._repository.latest_metadata_for_work(work.id)

    def _resolve_initial(
        self,
        *,
        plain_text: str | None,
        html: str | None,
        metadata_updates: Mapping[str, object] | None,
        restore_revision: int | None,
        expected_parent_draft_id: int | None,
    ) -> tuple[int, None, NovelDocument, dict[str, str]]:
        if expected_parent_draft_id is not None:
            raise VersionConflictError("VERSION_CONFLICT")
        if restore_revision is not None:
            raise ValidationError(
                "restore_revision is not valid for an initial draft",
                field="restore_revision",
            )
        if plain_text is not None:
            return 1, None, import_plain_text(plain_text), {}
        if html is None:
            raise ValidationError(
                "exactly one initial draft source is required", field="html"
            )
        resolution = resolve_authoring(None, html, metadata_updates)
        return 1, None, resolution.document, resolution.id_map

    def _resolve_existing(
        self,
        *,
        work_id: int,
        episode_id: int,
        parent_document: NovelDocument,
        plain_text: str | None,
        html: str | None,
        metadata_updates: Mapping[str, object] | None,
        restore_revision: int | None,
    ) -> tuple[NovelDocument, dict[str, str]]:
        if plain_text is not None:
            raise ValidationError(
                "plain_text is only valid for the initial draft", field="plain_text"
            )
        if restore_revision is not None:
            historical = self._repository.get(
                work_id=work_id, episode_id=episode_id, revision=restore_revision
            )
            if historical is None:
                raise ValidationError(
                    "restore_revision does not exist in this episode",
                    field="restore_revision",
                )
            return self._snapshot_from_record(historical).document, {}
        if html is None and metadata_updates is None:
            raise ValidationError("html or metadata_updates is required", field="html")
        resolution = resolve_authoring(parent_document, html, metadata_updates)
        return resolution.document, resolution.id_map

    def _snapshot_from_record(self, record: DraftRecord) -> DraftSnapshot:
        try:
            document = parse_document_json(record.document_json)
        except DocumentSchemaError as exc:
            raise DocumentStorageError() from exc
        return DraftSnapshot(
            id=record.id,
            work_id=record.work_id,
            episode_id=record.episode_id,
            revision=record.revision,
            parent_draft_id=record.parent_draft_id,
            document=document,
            source_agent=record.source_agent,
            change_summary=record.change_summary,
            created_at=record.created_at,
        )

    def _validate_live_references(
        self,
        *,
        work_id: int,
        episode_id: int,
        parent: NovelDocument | None,
        document: NovelDocument,
    ) -> None:
        previous = (
            {} if parent is None else {block.id: block for block in parent.blocks}
        )
        for block in document.blocks:
            old = previous.get(block.id)
            old_attrs = None if old is None else old.attrs
            if block.attrs.scene_id is not None and (
                old_attrs is None or block.attrs.scene_id != old_attrs.scene_id
            ):
                scene = self._narrative_repository.get_scene(
                    work_id=work_id, scene_id=block.attrs.scene_id
                )
                if scene is None or scene.episode_id != episode_id:
                    raise ValidationError(
                        "scene_id must identify a scene in this episode",
                        field="scene_id",
                    )
            if block.attrs.speaker_character_id is not None and (
                old_attrs is None
                or block.attrs.speaker_character_id != old_attrs.speaker_character_id
            ):
                character_work_id = self._character_repository.get_work_id(
                    block.attrs.speaker_character_id
                )
                if character_work_id != work_id:
                    raise ValidationError(
                        "speaker_character_id must identify a character in this work",
                        field="speaker_character_id",
                    )

    def _validate_combination(
        self,
        plain_text: str | None,
        html: str | None,
        metadata_updates: Mapping[str, object] | None,
        restore_revision: int | None,
    ) -> None:
        if plain_text is not None and html is not None:
            raise ValidationError("plain_text and html are mutually exclusive")
        if restore_revision is not None and any(
            value is not None for value in (plain_text, html, metadata_updates)
        ):
            raise ValidationError("restore_revision is mutually exclusive")
        if plain_text is not None and metadata_updates is not None:
            raise ValidationError(
                "plain_text cannot be combined with metadata_updates",
                field="metadata_updates",
            )

    def _validate_episode(self, episode_id: int) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        episode = self._narrative_repository.get_episode(
            work_id=work.id, episode_id=episode_id
        )
        if episode is not None:
            return work.id
        if self._narrative_repository.get_episode_work_id(episode_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _validate_optional_text(self, value: object, field: str) -> None:
        if value is not None and not isinstance(value, str):
            raise ValidationError(f"{field} must be a string", field=field)

    def _validate_source_agent(self, value: object) -> None:
        if value is not None and (
            not isinstance(value, str) or not 1 <= len(value) <= 120
        ):
            raise ValidationError(
                "source_agent must contain 1 to 120 characters", field="source_agent"
            )

    def _validate_change_summary(self, value: object) -> None:
        if not isinstance(value, str) or len(value) > 1000:
            raise ValidationError(
                "change_summary must contain at most 1000 characters",
                field="change_summary",
            )

    def _validate_limit(self, value: object) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= 100
        ):
            raise ValidationError("limit must be between 1 and 100", field="limit")

    def _validate_positive_int(self, value: object, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError(f"{field} must be at least 1", field=field)

    def _validate_optional_positive_int(self, value: object, field: str) -> None:
        if value is not None:
            self._validate_positive_int(value, field)
