from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from typing import cast

from novel_mcp.errors import (
    CanonDecisionNotFoundError,
    CanonEntityNotFoundError,
    CanonPolicyError,
    CanonReasonRequired,
    ValidationError,
    VersionConflictError,
    WorkNotFoundError,
)
from novel_mcp.repositories.canon_repository import (
    CanonChange,
    CanonDecisionRecord,
    CanonRepository,
)
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.services.search_service import MAX_SEARCH_LIMIT


class CanonService:
    _STATUSES = frozenset(("idea", "draft", "canon", "deprecated"))
    _ENTITY_TYPES = frozenset(
        ("world_fact", "timeline_event", "character", "relationship")
    )
    _ALLOWED_TRANSITIONS = frozenset(
        {
            ("idea", "draft"),
            ("idea", "canon"),
            ("draft", "canon"),
            ("canon", "deprecated"),
            ("deprecated", "draft"),
        }
    )

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._repository = CanonRepository(connection)
        self._work_repository = WorkRepository(connection)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    @property
    def repository(self) -> CanonRepository:
        return self._repository

    def set_canon_status(
        self,
        entity_type: str,
        entity_id: int,
        target_status: str,
        expected_version: int,
        reason: str | None = None,
    ) -> CanonDecisionRecord:
        self._validate_entity_type(entity_type)
        self._validate_status(target_status)
        work_id = self._work_id()
        self._repository.begin_write()
        try:
            before = self._entity_or_not_found(work_id, entity_type, entity_id)
            if cast(int, before["version"]) != expected_version:
                raise VersionConflictError("VERSION_CONFLICT")
            current_status = before["canon_status"]
            if current_status == target_status:
                raise CanonPolicyError("target status is unchanged")
            if (current_status, target_status) not in self._ALLOWED_TRANSITIONS:
                raise CanonPolicyError(
                    f"transition {current_status}->{target_status} is not allowed"
                )
            if (current_status in ("idea", "draft") and target_status == "canon") or (
                current_status == "canon" and target_status == "deprecated"
            ):
                self._require_reason(reason)
            change = CanonChange(
                entity_type,
                entity_id,
                "status_changed",
                before,
                {
                    **before,
                    "canon_status": target_status,
                    "version": cast(int, before["version"]) + 1,
                },
            )
            if not self._repository.update_status(
                work_id=work_id,
                entity_type=entity_type,
                entity_id=entity_id,
                expected_version=expected_version,
                target_status=target_status,
            ):
                raise VersionConflictError("VERSION_CONFLICT")
            decision_id = self._repository.insert_decision(
                work_id=work_id,
                summary=(
                    f"Set {entity_type} {entity_id} canon status to {target_status}"
                ),
                reason=reason or "",
                changes=(change,),
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        return self._decision_or_not_found(work_id, decision_id)

    def update_content(
        self,
        entity_type: str,
        entity_id: int,
        fields: Mapping[str, object],
        *,
        expected_version: int,
        reason: str | None = None,
        after_update: Callable[[], None] | None = None,
        allow_empty: bool = False,
    ) -> CanonDecisionRecord | None:
        self._validate_entity_type(entity_type)
        work_id = self._work_id()
        normalized = dict(fields)
        self._repository.begin_write()
        try:
            before = self._entity_or_not_found(work_id, entity_type, entity_id)
            if cast(int, before["version"]) != expected_version:
                raise VersionConflictError("VERSION_CONFLICT")
            if before["canon_status"] == "canon":
                self._require_reason(reason)
            elif before["canon_status"] == "deprecated":
                raise CanonPolicyError("deprecated content cannot be edited")
            after = {
                **before,
                **normalized,
                "version": cast(int, before["version"]) + 1,
            }
            change = CanonChange(
                entity_type, entity_id, "content_changed", before, after
            )
            updated = self._repository.update_content(
                work_id=work_id,
                entity_type=entity_type,
                entity_id=entity_id,
                expected_version=expected_version,
                fields=normalized,
                allow_empty=allow_empty,
            )
            if updated is None:
                raise CanonPolicyError("invalid content fields")
            if not updated:
                raise VersionConflictError("VERSION_CONFLICT")
            if after_update is not None:
                after_update()
            decision_id: int | None = None
            if before["canon_status"] == "canon":
                decision_id = self._repository.insert_decision(
                    work_id=work_id,
                    summary=f"Update {entity_type} {entity_id} content",
                    reason=reason or "",
                    changes=(change,),
                )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        if decision_id is None:
            return None
        return self._decision_or_not_found(work_id, decision_id)

    def record_decision(
        self, summary: str, reason: str, changes: Sequence[CanonChange]
    ) -> CanonDecisionRecord:
        normalized_summary = self._required_text(summary, "summary")
        normalized_reason = self._required_text(reason, "reason")
        normalized_changes = tuple(changes)
        if not normalized_changes:
            raise ValidationError("changes must be non-empty", field="changes")
        work_id = self._work_id()
        for change in normalized_changes:
            self._validate_entity_type(change.entity_type)
            self._entity_or_not_found(work_id, change.entity_type, change.entity_id)
        self._repository.begin_write()
        try:
            decision_id = self._repository.insert_decision(
                work_id=work_id,
                summary=normalized_summary,
                reason=normalized_reason,
                changes=normalized_changes,
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        return self._decision_or_not_found(work_id, decision_id)

    def get_decision(self, decision_id: int) -> CanonDecisionRecord:
        return self._decision_or_not_found(self._work_id(), decision_id)

    def search_decisions(
        self, query: str, limit: int
    ) -> tuple[CanonDecisionRecord, ...]:
        normalized = query.strip()
        if not normalized or limit <= 0:
            return ()
        return self._repository.search_decisions(
            work_id=self._work_id(),
            query=normalized,
            limit=min(limit, MAX_SEARCH_LIMIT),
        )

    def _entity_or_not_found(
        self, work_id: int, entity_type: str, entity_id: int
    ) -> dict[str, object]:
        record = self._repository.get_entity(
            work_id=work_id, entity_type=entity_type, entity_id=entity_id
        )
        if record is None:
            raise CanonEntityNotFoundError()
        return record

    def _decision_or_not_found(
        self, work_id: int, decision_id: int
    ) -> CanonDecisionRecord:
        record = self._repository.get_decision(work_id=work_id, decision_id=decision_id)
        if record is None:
            raise CanonDecisionNotFoundError()
        return record

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _validate_entity_type(self, value: str) -> None:
        if value not in self._ENTITY_TYPES:
            raise ValidationError("unsupported entity_type", field="entity_type")

    def _validate_status(self, value: str) -> None:
        if value not in self._STATUSES:
            raise ValidationError("unsupported canon status", field="target_status")

    def _require_reason(self, reason: str | None) -> None:
        if reason is None or not reason.strip():
            raise CanonReasonRequired()

    def _required_text(self, value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be non-empty", field=field_name)
        return value.strip()
