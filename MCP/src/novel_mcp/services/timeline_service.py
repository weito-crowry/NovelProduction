from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date
from uuid import uuid4

from novel_mcp.errors import (
    CanonEntityNotFoundError,
    TimelineEventNotFoundError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_mcp.repositories.timeline_repository import (
    TimelineEventRecord,
    TimelineRelationRecord,
    TimelineRepository,
)
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.search_service import MAX_SEARCH_LIMIT


class TimelineService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._work_repository = WorkRepository(connection)
        self._repository = TimelineRepository(connection)
        self._canon_service = CanonService(connection)

    def create_event(
        self,
        event_date: str,
        title: str,
        *,
        participants: Sequence[tuple[str, str]],
    ) -> TimelineEventRecord:
        normalized_date = self._normalize_date(event_date)
        normalized_title = self._normalize_text(title, "title")
        normalized_participants = self._normalize_participants(participants)
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            event_id = self._repository.create(
                work_id=work_id,
                event_key=uuid4().hex,
                title=normalized_title,
                chronology_sort_key=normalized_date,
            )
            for label, role in normalized_participants:
                self._repository.add_participant(
                    event_id=event_id, label=label, role=role
                )
            record = self._repository.get(work_id=work_id, event_id=event_id)
            if record is None:
                raise sqlite3.IntegrityError("timeline event creation failed")
            self._repository.commit()
            return record
        except Exception:
            self._repository.rollback()
            raise

    def get_event(self, event_id: int) -> TimelineEventRecord:
        record = self._repository.get(work_id=self._work_id(), event_id=event_id)
        if record is None:
            raise TimelineEventNotFoundError("NOT_FOUND")
        return record

    def update_event(
        self,
        event_id: int,
        expected_version: int,
        *,
        title: str | None = None,
        new_date: str | None = None,
        participants: Sequence[tuple[str, str]] | None = None,
        reason: str | None = None,
    ) -> TimelineEventRecord:
        normalized_title = (
            self._normalize_text(title, "title") if title is not None else None
        )
        normalized_date = (
            self._normalize_date(new_date) if new_date is not None else None
        )
        normalized_participants = (
            self._normalize_participants(participants)
            if participants is not None
            else None
        )
        try:
            fields: dict[str, object] = {}
            if normalized_title is not None:
                fields.update(title=normalized_title, summary=normalized_title)
            if normalized_date is not None:
                fields["chronology_sort_key"] = normalized_date

            def update_participants() -> None:
                if normalized_participants is not None:
                    self._repository.replace_participants(
                        event_id=event_id,
                        participants=normalized_participants,
                    )

            self._canon_service.update_content(
                "timeline_event",
                event_id,
                fields,
                expected_version=expected_version,
                reason=reason,
                after_update=update_participants,
                allow_empty=True,
            )
        except CanonEntityNotFoundError as exc:
            raise TimelineEventNotFoundError("NOT_FOUND") from exc
        return self.get_event(event_id)

    def search_events(self, query: str, limit: int) -> tuple[TimelineEventRecord, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0:
            return ()
        return self._repository.search(
            work_id=self._work_id(),
            query=normalized_query,
            limit=min(limit, MAX_SEARCH_LIMIT),
        )

    def range_events(
        self, start: str, end: str, limit: int
    ) -> tuple[TimelineEventRecord, ...]:
        normalized_start = self._normalize_date(start)
        normalized_end = self._normalize_date(end)
        if normalized_start > normalized_end:
            raise ValueError("end must be on or after start")
        if limit <= 0:
            return ()
        return self._repository.range(
            work_id=self._work_id(),
            start=normalized_start,
            end=normalized_end,
            limit=min(limit, MAX_SEARCH_LIMIT),
        )

    def move_event(
        self,
        event_id: int,
        expected_version: int,
        new_date: str,
        reason: str | None = None,
    ) -> TimelineEventRecord:
        return self.update_event(
            event_id,
            expected_version,
            new_date=new_date,
            reason=reason,
        )

    def create_relation(
        self, source_id: int, target_id: int, relation_type: str
    ) -> TimelineRelationRecord:
        normalized_type = self._normalize_text(relation_type, "relation_type")
        work_id = self._work_id()
        self._require_event_in_work(work_id, source_id)
        self._require_event_in_work(work_id, target_id)
        if source_id == target_id:
            raise ValueError("self relation is not allowed")
        self._repository.begin_write()
        try:
            try:
                relation = self._repository.create_relation(
                    work_id=work_id,
                    source_event_id=source_id,
                    target_event_id=target_id,
                    relation_type=normalized_type,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("duplicate relation") from exc
            self._repository.commit()
            return relation
        except Exception:
            self._repository.rollback()
            raise

    def _require_event_in_work(self, work_id: int, event_id: int) -> None:
        if self._repository.get(work_id=work_id, event_id=event_id) is not None:
            return
        if self._repository.get_work_id(event_id) is not None:
            raise WorkScopeError()
        raise TimelineEventNotFoundError("NOT_FOUND")

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _normalize_date(self, value: str) -> str:
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except (AttributeError, ValueError) as exc:
            raise ValueError("date must be YYYY-MM-DD") from exc

    def _normalize_text(self, value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must be non-empty")
        return normalized

    def _normalize_participants(
        self, participants: Sequence[tuple[str, str]]
    ) -> tuple[tuple[str, str], ...]:
        normalized = tuple(
            (
                self._normalize_text(label, "participant label"),
                self._normalize_text(role, "participant role"),
            )
            for label, role in participants
        )
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate participant")
        return normalized
