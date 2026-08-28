from __future__ import annotations

import sqlite3

from novel_core.errors import (
    CanonEntityNotFoundError,
    CharacterNotFoundError,
    NarrativeNotFoundError,
    RelationshipIntegrityError,
    RelationshipNotFoundError,
    ValidationError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_core.repositories.character_repository import CharacterRepository
from novel_core.repositories.narrative_repository import NarrativeRepository
from novel_core.repositories.relationship_repository import (
    RelationshipRecord,
    RelationshipRepository,
)
from novel_core.repositories.work_repository import WorkRepository
from novel_core.services.canon_service import CanonService
from novel_core.services.search_service import MAX_SEARCH_LIMIT


class RelationshipService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._work_repository = WorkRepository(connection)
        self._character_repository = CharacterRepository(connection)
        self._narrative_repository = NarrativeRepository(connection)
        self._repository = RelationshipRepository(connection)
        self._canon_service = CanonService(connection)

    def create(
        self,
        source_character_id: int,
        target_character_id: int,
        relation_type: str,
        description: str = "",
        *,
        valid_from_episode_id: int | None = None,
        valid_to_episode_id: int | None = None,
    ) -> RelationshipRecord:
        normalized_type = self._required_text(relation_type, "relation_type")
        normalized_description = self._optional_text(description, "description")
        work_id = self._work_id()
        self._validate_endpoint(work_id, source_character_id)
        self._validate_endpoint(work_id, target_character_id)
        if source_character_id == target_character_id:
            raise ValidationError("self relationship is not allowed", field="endpoints")
        self._validate_interval(work_id, valid_from_episode_id, valid_to_episode_id)
        self._repository.begin_write()
        try:
            try:
                self._check_overlap(
                    work_id=work_id,
                    source_character_id=source_character_id,
                    target_character_id=target_character_id,
                    relationship_type=normalized_type,
                    valid_from_episode_id=valid_from_episode_id,
                    valid_to_episode_id=valid_to_episode_id,
                )
                relationship_id = self._repository.create(
                    work_id=work_id,
                    source_character_id=source_character_id,
                    target_character_id=target_character_id,
                    relationship_type=normalized_type,
                    description=normalized_description,
                    valid_from_episode_id=valid_from_episode_id,
                    valid_to_episode_id=valid_to_episode_id,
                )
            except sqlite3.IntegrityError as exc:
                raise RelationshipIntegrityError(
                    "relationship could not be stored"
                ) from exc
            record = self._repository.get(
                work_id=work_id, relationship_id=relationship_id
            )
            if record is None:
                raise sqlite3.IntegrityError("relationship creation failed")
            self._repository.commit()
            return record
        except Exception:
            self._repository.rollback()
            raise

    def get(self, relationship_id: int) -> RelationshipRecord:
        record = self._repository.get(
            work_id=self._work_id(), relationship_id=relationship_id
        )
        if record is None:
            raise RelationshipNotFoundError("NOT_FOUND")
        return record

    def update(
        self,
        relationship_id: int,
        expected_version: int,
        relation_type: str,
        reason: str | None = None,
        *,
        relationship_type: str | None = None,
        description: str | None = None,
        valid_from_episode_id: int | None = None,
        valid_to_episode_id: int | None = None,
        clear_valid_from: bool = False,
        clear_valid_to: bool = False,
    ) -> RelationshipRecord:
        if valid_from_episode_id is not None and clear_valid_from:
            raise ValidationError(
                "valid_from_episode_id cannot be combined with clear_valid_from",
                field="valid_from_episode_id",
            )
        if valid_to_episode_id is not None and clear_valid_to:
            raise ValidationError(
                "valid_to_episode_id cannot be combined with clear_valid_to",
                field="valid_to_episode_id",
            )
        normalized_type = self._required_text(
            relationship_type if relationship_type is not None else relation_type,
            "relationship_type",
        )
        work_id = self._work_id()
        current = self._repository.get(work_id=work_id, relationship_id=relationship_id)
        if current is None:
            raise RelationshipNotFoundError("NOT_FOUND")
        next_from = (
            None
            if clear_valid_from
            else valid_from_episode_id
            if valid_from_episode_id is not None
            else current.valid_from_episode_id
        )
        next_to = (
            None
            if clear_valid_to
            else valid_to_episode_id
            if valid_to_episode_id is not None
            else current.valid_to_episode_id
        )
        self._validate_interval(work_id, next_from, next_to)

        def check_overlap() -> None:
            self._check_overlap(
                work_id=work_id,
                source_character_id=current.source_character_id,
                target_character_id=current.target_character_id,
                relationship_type=normalized_type,
                valid_from_episode_id=next_from,
                valid_to_episode_id=next_to,
                exclude_id=relationship_id,
            )

        fields = {
            "relationship_type": normalized_type,
            **(
                {"description": self._optional_text(description, "description")}
                if description is not None
                else {}
            ),
            **(
                {"valid_from_episode_id": next_from}
                if clear_valid_from or valid_from_episode_id is not None
                else {}
            ),
            **(
                {"valid_to_episode_id": next_to}
                if clear_valid_to or valid_to_episode_id is not None
                else {}
            ),
        }
        try:
            self._canon_service.update_content(
                "relationship",
                relationship_id,
                fields,
                expected_version=expected_version,
                reason=reason,
                before_update=check_overlap,
            )
        except CanonEntityNotFoundError as exc:
            raise RelationshipNotFoundError("NOT_FOUND") from exc
        return self.get(relationship_id)

    def effective_at(
        self, episode_id: int, character_id: int | None = None
    ) -> tuple[RelationshipRecord, ...]:
        work_id = self._work_id()
        target_order = self._episode_order(work_id, episode_id)
        assert target_order is not None
        records = self._repository.list_all(work_id=work_id)
        effective: list[RelationshipRecord] = []
        for record in records:
            if record.canon_status == "deprecated":
                continue
            if character_id is not None and character_id not in (
                record.source_character_id,
                record.target_character_id,
            ):
                continue
            if self._interval_contains(work_id, record, target_order):
                effective.append(record)
        return tuple(effective)

    def search(
        self, character_id: int | None, limit: int
    ) -> tuple[RelationshipRecord, ...]:
        if limit <= 0:
            return ()
        work_id = self._work_id()
        if character_id is not None:
            self._validate_endpoint(work_id, character_id)
        return self._repository.search(
            work_id=work_id,
            character_id=character_id,
            limit=min(limit, MAX_SEARCH_LIMIT),
        )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _validate_endpoint(self, work_id: int, character_id: int) -> None:
        if (
            self._character_repository.get(work_id=work_id, character_id=character_id)
            is not None
        ):
            return
        if self._character_repository.get_work_id(character_id) is not None:
            raise WorkScopeError()
        raise CharacterNotFoundError("NOT_FOUND")

    def _validate_interval(
        self,
        work_id: int,
        valid_from_episode_id: int | None,
        valid_to_episode_id: int | None,
    ) -> None:
        for field, episode_id in (
            ("valid_from_episode_id", valid_from_episode_id),
            ("valid_to_episode_id", valid_to_episode_id),
        ):
            if episode_id is not None and (
                isinstance(episode_id, bool)
                or not isinstance(episode_id, int)
                or episode_id < 1
            ):
                raise ValidationError(
                    f"{field} must be a positive integer", field=field
                )
        start = self._episode_order(work_id, valid_from_episode_id)
        end = self._episode_order(work_id, valid_to_episode_id)
        if start is not None and end is not None and start >= end:
            raise RelationshipIntegrityError("valid_to must follow valid_from")

    def _episode_order(
        self, work_id: int, episode_id: int | None
    ) -> tuple[int, int] | None:
        if episode_id is None:
            return None
        order = self._narrative_repository.get_episode_narrative_order(
            work_id=work_id, episode_id=episode_id
        )
        if order is not None:
            return order
        if self._narrative_repository.get_episode_work_id(episode_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _check_overlap(
        self,
        *,
        work_id: int,
        source_character_id: int,
        target_character_id: int,
        relationship_type: str,
        valid_from_episode_id: int | None,
        valid_to_episode_id: int | None,
        exclude_id: int | None = None,
    ) -> None:
        for existing in self._repository.find_same_definition(
            work_id=work_id,
            source_character_id=source_character_id,
            target_character_id=target_character_id,
            relationship_type=relationship_type,
            exclude_id=exclude_id,
        ):
            if self._intervals_overlap(
                work_id,
                valid_from_episode_id,
                valid_to_episode_id,
                existing.valid_from_episode_id,
                existing.valid_to_episode_id,
            ):
                raise RelationshipIntegrityError()

    def _intervals_overlap(
        self,
        work_id: int,
        left_from: int | None,
        left_to: int | None,
        right_from: int | None,
        right_to: int | None,
    ) -> bool:
        start_floor = (-1, -1)
        end_ceiling = (10**18, 10**18)
        left_start = (
            start_floor
            if left_from is None
            else self._episode_order(work_id, left_from)
        )
        left_end = (
            end_ceiling if left_to is None else self._episode_order(work_id, left_to)
        )
        right_start = (
            start_floor
            if right_from is None
            else self._episode_order(work_id, right_from)
        )
        right_end = (
            end_ceiling if right_to is None else self._episode_order(work_id, right_to)
        )
        assert left_start is not None
        assert left_end is not None
        assert right_start is not None
        assert right_end is not None
        return left_start < right_end and right_start < left_end

    def _interval_contains(
        self,
        work_id: int,
        record: RelationshipRecord,
        target_order: tuple[int, int],
    ) -> bool:
        start = (
            (-1, -1)
            if record.valid_from_episode_id is None
            else self._episode_order(work_id, record.valid_from_episode_id)
        )
        end = (
            (10**18, 10**18)
            if record.valid_to_episode_id is None
            else self._episode_order(work_id, record.valid_to_episode_id)
        )
        assert start is not None
        assert end is not None
        return start <= target_order < end

    def _required_text(self, value: str, field_name: str) -> str:
        try:
            normalized = value.strip()
        except AttributeError as exc:
            raise ValidationError(
                f"{field_name} must be a string", field=field_name
            ) from exc
        if not normalized:
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return normalized

    def _optional_text(self, value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field=field_name)
        return value.strip()
