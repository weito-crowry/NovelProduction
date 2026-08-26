from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from typing import cast

from novel_mcp.errors import (
    CanonDecisionNotFoundError,
    CanonPolicyError,
    CanonReasonRequired,
    ValidationError,
    WorkNotFoundError,
)
from novel_mcp.repositories.canon_repository import (
    CanonChange,
    CanonDecisionRecord,
    CanonRepository,
)
from novel_mcp.repositories.work_repository import WorkRepository


class CanonService:
    _STATUSES = frozenset(("idea", "draft", "canon", "deprecated"))
    _ENTITY_TYPES = frozenset(
        ("world_fact", "timeline_event", "character", "relationship")
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
        self, entity_type: str, entity_id: int, target_status: str, reason: str | None
    ) -> CanonDecisionRecord:
        self._validate_entity_type(entity_type)
        self._validate_status(target_status)
        work_id = self._work_id()
        before = self._entity_or_not_found(work_id, entity_type, entity_id)
        current_status = before["canon_status"]
        if current_status == target_status:
            raise CanonPolicyError("target status is unchanged")
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
        return self._mutate_and_record(
            work_id,
            entity_type,
            entity_id,
            lambda: self._repository.update_status(
                work_id=work_id,
                entity_type=entity_type,
                entity_id=entity_id,
                target_status=target_status,
            ),
            f"Set {entity_type} {entity_id} canon status to {target_status}",
            reason or "",
            change,
        )

    def update_content(
        self,
        entity_type: str,
        entity_id: int,
        fields: Mapping[str, object],
        *,
        reason: str | None,
    ) -> CanonDecisionRecord:
        self._validate_entity_type(entity_type)
        work_id = self._work_id()
        before = self._entity_or_not_found(work_id, entity_type, entity_id)
        if before["canon_status"] == "canon":
            self._require_reason(reason)
        normalized = dict(fields)
        after = {
            **before,
            **normalized,
            "version": cast(int, before["version"]) + 1,
        }
        change = CanonChange(entity_type, entity_id, "content_changed", before, after)
        return self._mutate_and_record(
            work_id,
            entity_type,
            entity_id,
            lambda: self._repository.update_content(
                work_id=work_id,
                entity_type=entity_type,
                entity_id=entity_id,
                fields=normalized,
            ),
            f"Update {entity_type} {entity_id} content",
            reason or "ordinary authoring edit",
            change,
        )

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
            work_id=self._work_id(), query=normalized, limit=limit
        )

    def _mutate_and_record(
        self,
        work_id: int,
        entity_type: str,
        entity_id: int,
        mutate: Callable[[], bool],
        summary: str,
        reason: str,
        change: CanonChange,
    ) -> CanonDecisionRecord:
        self._repository.begin_write()
        try:
            if not mutate():
                raise CanonPolicyError("canon target was not updated")
            decision_id = self._repository.insert_decision(
                work_id=work_id, summary=summary, reason=reason, changes=(change,)
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        return self._decision_or_not_found(work_id, decision_id)

    def _entity_or_not_found(
        self, work_id: int, entity_type: str, entity_id: int
    ) -> dict[str, object]:
        record = self._repository.get_entity(
            work_id=work_id, entity_type=entity_type, entity_id=entity_id
        )
        if record is None:
            raise RuntimeError("NOT_FOUND")
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
