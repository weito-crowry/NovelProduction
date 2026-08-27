from __future__ import annotations

import hashlib
import sqlite3

from novel_core.errors import (
    NarrativeNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_core.repositories.draft_repository import (
    DraftMetadata,
    DraftRecord,
    DraftRepository,
)
from novel_core.repositories.narrative_repository import NarrativeRepository
from novel_core.repositories.work_repository import WorkRepository


class DraftService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = DraftRepository(connection)
        self._narrative_repository = NarrativeRepository(connection)
        self._work_repository = WorkRepository(connection)

    def save_draft(
        self,
        episode_id: int,
        body: str,
        expected_parent_draft_id: int | None = None,
        source_agent: str | None = None,
        change_summary: str = "",
    ) -> DraftRecord:
        self._validate_positive_int(episode_id, "episode_id")
        self._validate_body(body)
        self._validate_optional_positive_int(
            expected_parent_draft_id, "expected_parent_draft_id"
        )
        self._validate_source_agent(source_agent)
        self._validate_change_summary(change_summary)
        work_id = self._validate_episode(episode_id)
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        self._repository.begin_write()
        try:
            latest = self._repository.latest(work_id=work_id, episode_id=episode_id)
            if latest is None:
                if expected_parent_draft_id is not None:
                    raise VersionConflictError("VERSION_CONFLICT")
                revision = 1
                parent_draft_id = None
            else:
                if expected_parent_draft_id != latest.id:
                    raise VersionConflictError("VERSION_CONFLICT")
                revision = latest.revision + 1
                parent_draft_id = latest.id
            draft_id = self._repository.insert(
                work_id=work_id,
                episode_id=episode_id,
                revision=revision,
                parent_draft_id=parent_draft_id,
                body=body,
                source_agent=source_agent,
                change_summary=change_summary,
                content_hash=content_hash,
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise

        result = self._repository.get(
            work_id=work_id, episode_id=episode_id, revision=revision
        )
        if result is None or result.id != draft_id:
            raise sqlite3.IntegrityError("draft retrieval failed")
        return result

    def get_draft(
        self, episode_id: int, revision: int | None = None
    ) -> DraftRecord | None:
        self._validate_positive_int(episode_id, "episode_id")
        if revision is not None:
            self._validate_positive_int(revision, "revision")
        work_id = self._validate_episode(episode_id)
        return self._repository.get(
            work_id=work_id, episode_id=episode_id, revision=revision
        )

    def history(self, episode_id: int, limit: int = 20) -> tuple[DraftMetadata, ...]:
        self._validate_positive_int(episode_id, "episode_id")
        self._validate_limit(limit)
        work_id = self._validate_episode(episode_id)
        return self._repository.history(
            work_id=work_id, episode_id=episode_id, limit=limit
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

    def _validate_body(self, value: object) -> None:
        if not isinstance(value, str) or len(value) == 0:
            raise ValidationError("body must be a non-empty string", field="body")

    def _validate_source_agent(self, value: object) -> None:
        if value is not None and (
            not isinstance(value, str) or not 1 <= len(value) <= 120
        ):
            raise ValidationError(
                "source_agent must contain 1 to 120 characters",
                field="source_agent",
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
