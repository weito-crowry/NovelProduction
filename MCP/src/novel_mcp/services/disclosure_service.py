from __future__ import annotations

import sqlite3

from novel_mcp.errors import (
    NarrativeNotFoundError,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
    WorkScopeError,
)
from novel_mcp.repositories.disclosure_repository import (
    DisclosureRepository,
    ReaderDisclosureRecord,
)
from novel_mcp.repositories.information_repository import (
    InformationItemRecord,
    InformationRepository,
)
from novel_mcp.repositories.narrative_repository import NarrativeRepository
from novel_mcp.repositories.work_repository import WorkRepository


class DisclosureService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._repository = DisclosureRepository(connection)
        self._information_repository = InformationRepository(connection)
        self._narrative_repository = NarrativeRepository(connection)
        self._work_repository = WorkRepository(connection)

    def set_reader_disclosure(
        self,
        information_item_id: int,
        episode_id: int,
        *,
        expected_version: int | None = None,
    ) -> ReaderDisclosureRecord:
        work_id = self._work_id()
        self._validate_information(work_id, information_item_id)
        self._validate_episode(work_id, episode_id)
        self._validate_optional_version(expected_version)
        self._repository.begin_write()
        try:
            current = self._repository.get(
                work_id=work_id, information_item_id=information_item_id
            )
            if current is None:
                if expected_version is not None:
                    raise ValidationError(
                        "expected_version must be None for a new disclosure",
                        field="expected_version",
                    )
                disclosure_id = self._repository.create(
                    work_id=work_id,
                    information_item_id=information_item_id,
                    episode_id=episode_id,
                )
            else:
                if expected_version is None:
                    raise ValidationError(
                        "expected_version is required for an existing disclosure",
                        field="expected_version",
                    )
                if current.episode_id == episode_id:
                    self._repository.commit()
                    return current
                if not self._repository.update(
                    work_id=work_id,
                    information_item_id=information_item_id,
                    episode_id=episode_id,
                    expected_version=expected_version,
                ):
                    raise VersionConflictError("VERSION_CONFLICT")
                disclosure_id = current.id
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        result = self._repository.get(
            work_id=work_id, information_item_id=information_item_id
        )
        if result is None or result.id != disclosure_id:
            raise sqlite3.IntegrityError("reader disclosure retrieval failed")
        return result

    def get_reader_disclosure(
        self, information_item_id: int
    ) -> ReaderDisclosureRecord | None:
        work_id = self._work_id()
        self._validate_information(work_id, information_item_id)
        return self._repository.get(
            work_id=work_id, information_item_id=information_item_id
        )

    def known_before(
        self, information_item_id: int, episode_id: int
    ) -> tuple[InformationItemRecord, ...]:
        item, boundary = self._boundary(information_item_id, episode_id)
        if boundary < self._episode_order(item.work_id, episode_id):
            return (item,)
        return ()

    def reveal_this_episode(
        self, information_item_id: int, episode_id: int
    ) -> tuple[InformationItemRecord, ...]:
        item, boundary = self._boundary(information_item_id, episode_id)
        if boundary == self._episode_order(item.work_id, episode_id):
            return (item,)
        return ()

    def _boundary(
        self, information_item_id: int, episode_id: int
    ) -> tuple[InformationItemRecord, tuple[int, int]]:
        work_id = self._work_id()
        item = self._validate_information(work_id, information_item_id)
        self._validate_episode(work_id, episode_id)
        disclosure = self._repository.get(
            work_id=work_id, information_item_id=information_item_id
        )
        if disclosure is None:
            return item, (10**18, 10**18)
        return item, self._episode_order(work_id, disclosure.episode_id)

    def _episode_order(self, work_id: int, episode_id: int) -> tuple[int, int]:
        order = self._narrative_repository.get_episode_narrative_order(
            work_id=work_id, episode_id=episode_id
        )
        if order is None:
            raise NarrativeNotFoundError()
        return order

    def _validate_information(
        self, work_id: int, information_item_id: int
    ) -> InformationItemRecord:
        item = self._information_repository.get(
            work_id=work_id, item_id=information_item_id
        )
        if item is not None:
            return item
        if self._information_repository.get_work_id(information_item_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _validate_episode(self, work_id: int, episode_id: int) -> None:
        if self._narrative_repository.get_episode(
            work_id=work_id, episode_id=episode_id
        ):
            return
        if self._narrative_repository.get_episode_work_id(episode_id) is not None:
            raise WorkScopeError()
        raise NarrativeNotFoundError()

    def _validate_optional_version(self, value: int | None) -> None:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ValidationError(
                "expected_version must be at least 1", field="expected_version"
            )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id
