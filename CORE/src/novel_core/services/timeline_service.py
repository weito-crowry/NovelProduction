from __future__ import annotations

import calendar
import re
import sqlite3
from collections.abc import Sequence
from datetime import date
from uuid import uuid4

from novel_core.errors import (
    CanonEntityNotFoundError,
    TimelineEventNotFoundError,
    ValidationError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_core.repositories.character_repository import CharacterRepository
from novel_core.repositories.timeline_repository import (
    TimelineEventRecord,
    TimelineRelationRecord,
    TimelineRepository,
)
from novel_core.repositories.work_repository import WorkRepository
from novel_core.repositories.world_fact_repository import WorldFactRepository
from novel_core.services.canon_service import CanonService
from novel_core.services.search_service import MAX_SEARCH_LIMIT

_DATE_PRECISIONS = frozenset(("unknown", "year", "season", "month", "day"))
_SEASONS = {"春": (3, 5), "夏": (6, 8), "秋": (9, 11)}


class TimelineService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._repository = TimelineRepository(connection)
        self._character_repository = CharacterRepository(connection)
        self._world_fact_repository = WorldFactRepository(connection)
        self._work_repository = WorkRepository(connection)
        self._canon_service = CanonService(connection)

    def create_event(
        self,
        event_date: str | None = None,
        title: str = "",
        *,
        participants: Sequence[tuple[int, str]] = (),
        event_key: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        date_precision: str | None = None,
        date_display: str | None = None,
        description: str = "",
        category: str = "general",
        location_world_fact_id: int | None = None,
        cause_summary: str = "",
        consequence_summary: str = "",
        importance: int = 0,
    ) -> TimelineEventRecord:
        normalized_title = self._required_text(title, "title")
        start, end, precision, display = self._normalize_date_range(
            event_date, time_start, time_end, date_precision, date_display
        )
        normalized_participants = self._normalize_participants(participants)
        work_id = self._work_id()
        self._validate_location(work_id, location_world_fact_id)
        self._validate_participants(work_id, normalized_participants)
        if not isinstance(importance, int) or importance < 0:
            raise ValidationError("importance must be non-negative", field="importance")
        fields: dict[str, object] = {
            "event_key": self._required_text(event_key or uuid4().hex, "event_key"),
            "time_start": start,
            "time_end": end,
            "date_precision": precision,
            "date_display": display,
            "title": normalized_title,
            "description": self._optional_text(description, "description"),
            "category": self._required_text(category, "category"),
            "location_world_fact_id": location_world_fact_id,
            "cause_summary": self._optional_text(cause_summary, "cause_summary"),
            "consequence_summary": self._optional_text(
                consequence_summary, "consequence_summary"
            ),
            "canon_status": "draft",
            "importance": importance,
        }
        self._repository.begin_write()
        try:
            event_id = self._repository.create(work_id=work_id, fields=fields)
            for character_id, role in normalized_participants:
                self._repository.add_participant(
                    event_id=event_id, character_id=character_id, role=role
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
        participants: Sequence[tuple[int, str]] | None = None,
        reason: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        date_precision: str | None = None,
        date_display: str | None = None,
        description: str | None = None,
        category: str | None = None,
        location_world_fact_id: int | None = None,
        cause_summary: str | None = None,
        consequence_summary: str | None = None,
        importance: int | None = None,
    ) -> TimelineEventRecord:
        current = self.get_event(event_id)
        fields: dict[str, object] = {}
        if title is not None:
            fields["title"] = self._required_text(title, "title")
        if description is not None:
            fields["description"] = self._optional_text(description, "description")
        for key, value in (
            ("category", category),
            ("cause_summary", cause_summary),
            ("consequence_summary", consequence_summary),
        ):
            if value is not None:
                fields[key] = self._optional_text(value, key)
        if importance is not None:
            if not isinstance(importance, int) or importance < 0:
                raise ValidationError(
                    "importance must be non-negative", field="importance"
                )
            fields["importance"] = importance
        if location_world_fact_id is not None:
            self._validate_location(self._work_id(), location_world_fact_id)
            fields["location_world_fact_id"] = location_world_fact_id
        if any(
            value is not None
            for value in (new_date, time_start, time_end, date_precision, date_display)
        ):
            start, end, precision, display = self._normalize_date_range(
                new_date,
                time_start,
                time_end,
                date_precision,
                date_display,
                current=current,
            )
            fields.update(
                time_start=start,
                time_end=end,
                date_precision=precision,
                date_display=display,
            )
        normalized_participants = (
            self._normalize_participants(participants)
            if participants is not None
            else None
        )
        if normalized_participants is not None:
            self._validate_participants(self._work_id(), normalized_participants)

        def update_participants() -> None:
            if normalized_participants is not None:
                self._repository.replace_participants(
                    event_id=event_id, participants=normalized_participants
                )

        if not fields and normalized_participants is None:
            fields["title"] = current.title
        try:
            self._canon_service.update_content(
                "timeline_event",
                event_id,
                fields,
                expected_version=expected_version,
                reason=reason,
                after_update=update_participants,
            )
        except CanonEntityNotFoundError as exc:
            raise TimelineEventNotFoundError("NOT_FOUND") from exc
        return self.get_event(event_id)

    def search_events(self, query: str, limit: int) -> tuple[TimelineEventRecord, ...]:
        normalized = query.strip()
        if not normalized or limit <= 0:
            return ()
        return self._repository.search(
            work_id=self._work_id(),
            query=normalized,
            limit=min(limit, MAX_SEARCH_LIMIT),
        )

    def list_events(self, limit: int, offset: int) -> tuple[TimelineEventRecord, ...]:
        if limit <= 0 or offset < 0:
            return ()
        return self._repository.list_events(
            work_id=self._work_id(),
            limit=limit,
            offset=offset,
        )

    def list_relations(
        self, event_id: int | None, limit: int, offset: int
    ) -> tuple[TimelineRelationRecord, ...]:
        if limit <= 0 or offset < 0:
            return ()
        return self._repository.list_relations(
            work_id=self._work_id(),
            event_id=event_id,
            limit=limit,
            offset=offset,
        )

    def range_events(
        self, start: str, end: str, limit: int
    ) -> tuple[TimelineEventRecord, ...]:
        normalized_start = self._exact_date(start, "start")
        normalized_end = self._exact_date(end, "end")
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
            event_id, expected_version, new_date=new_date, reason=reason
        )

    def create_relation(
        self, source_id: int, target_id: int, relation_type: str
    ) -> TimelineRelationRecord:
        normalized_type = self._required_text(relation_type, "relation_type")
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

    def _validate_location(self, work_id: int, fact_id: int | None) -> None:
        if fact_id is None:
            return
        if (
            self._world_fact_repository.get(work_id=work_id, fact_id=fact_id)
            is not None
        ):
            return
        if self._world_fact_repository.get_work_id(fact_id) is not None:
            raise WorkScopeError()
        raise ValidationError(
            "location world fact was not found", field="location_world_fact_id"
        )

    def _validate_participants(
        self, work_id: int, participants: tuple[tuple[int, str], ...]
    ) -> None:
        for character_id, _ in participants:
            if (
                self._character_repository.get(
                    work_id=work_id, character_id=character_id
                )
                is not None
            ):
                continue
            if self._character_repository.get_work_id(character_id) is not None:
                raise WorkScopeError()
            raise ValidationError(
                "participant character was not found", field="character_id"
            )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _normalize_date_range(
        self,
        event_date: str | None,
        time_start: str | None,
        time_end: str | None,
        date_precision: str | None,
        date_display: str | None,
        *,
        current: TimelineEventRecord | None = None,
    ) -> tuple[str | None, str | None, str, str]:
        if time_start is None and time_end is None and event_date is not None:
            start, end, parsed_precision = self._parse_human_date(event_date)
            return (
                start,
                end,
                date_precision or parsed_precision,
                date_display or event_date.strip(),
            )
        if (
            time_start is None
            and time_end is None
            and current is not None
            and date_precision is None
            and date_display is None
        ):
            return (
                current.time_start,
                current.time_end,
                current.date_precision,
                current.date_display,
            )
        normalized_start = (
            self._exact_date(time_start, "time_start") if time_start else None
        )
        normalized_end = (
            self._exact_date(time_end, "time_end") if time_end else normalized_start
        )
        precision = date_precision or ("day" if normalized_start else "unknown")
        if precision not in _DATE_PRECISIONS:
            raise ValidationError("unsupported date_precision", field="date_precision")
        if normalized_start is None and normalized_end is not None:
            raise ValueError("time_start is required when time_end is supplied")
        if normalized_start and normalized_end and normalized_start > normalized_end:
            raise ValueError("time_end must be on or after time_start")
        return (
            normalized_start,
            normalized_end,
            precision,
            date_display or "正確な日付不明",
        )

    def _parse_human_date(self, value: str) -> tuple[str | None, str | None, str]:
        normalized = self._required_text(value, "date_display")
        if normalized == "正確な日付不明":
            return None, None, "unknown"
        year_match = re.fullmatch(r"(\d{4})年", normalized)
        if year_match:
            year = int(year_match.group(1))
            return f"{year:04d}-01-01", f"{year:04d}-12-31", "year"
        season_match = re.fullmatch(r"(\d{4})年(春|夏|秋|冬)頃", normalized)
        if season_match:
            year, season = int(season_match.group(1)), season_match.group(2)
            if season == "冬":
                last_day = calendar.monthrange(year + 1, 2)[1]
                return (
                    f"{year:04d}-12-01",
                    f"{year + 1:04d}-02-{last_day:02d}",
                    "season",
                )
            month_start, month_end = _SEASONS[season]
            return (
                f"{year:04d}-{month_start:02d}-01",
                f"{year:04d}-{month_end:02d}-"
                f"{calendar.monthrange(year, month_end)[1]:02d}",
                "season",
            )
        month_match = re.fullmatch(r"(\d{4})年(\d{1,2})月頃", normalized)
        if month_match:
            year, month = int(month_match.group(1)), int(month_match.group(2))
            if not 1 <= month <= 12:
                raise ValueError("month must be between 1 and 12")
            return (
                f"{year:04d}-{month:02d}-01",
                f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}",
                "month",
            )
        exact = self._exact_date(normalized, "date_display")
        return exact, exact, "day"

    def _exact_date(self, value: str | None, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be YYYY-MM-DD")
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError as exc:
            raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc

    def _normalize_participants(
        self, participants: Sequence[tuple[int, str]]
    ) -> tuple[tuple[int, str], ...]:
        normalized = tuple(
            (self._character_id(character_id), self._required_text(role, "role"))
            for character_id, role in participants
        )
        if len(set(normalized)) != len(normalized):
            raise ValidationError("duplicate participant", field="participants")
        return normalized

    def _character_id(self, value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValidationError(
                "character_id must be a positive integer", field="character_id"
            )
        return value

    def _required_text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return value.strip()

    def _optional_text(self, value: object, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field=field_name)
        return value.strip()
