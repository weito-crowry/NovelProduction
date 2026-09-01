from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import cast

from novel_core.style_analysis.entity_models import (
    ENTITY_TYPES,
    MENTION_TYPES,
    EntityRecord,
)
from novel_core.style_analysis.entity_repository import EntityRepository
from novel_core.style_analysis.resolver_candidates import comparison_key


class EntityService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.repository = EntityRepository(connection)

    def exact_matches(
        self, *, document_id: int, surface: str
    ) -> tuple[EntityRecord, ...]:
        scope = self._scope(document_id)
        entities = self.repository.list_for_scope(**scope)
        matches: list[EntityRecord] = []
        key = comparison_key(surface)
        for entity in entities:
            if not self._enabled(entity.id):
                continue
            if comparison_key(self._effective_name(entity)) == key:
                matches.append(entity)
                continue
            for alias in self.repository.aliases_for(entity.id):
                if not self._alias_is_usable(alias.id, alias.origin):
                    continue
                if comparison_key(alias.alias) == key:
                    matches.append(entity)
                    break
        return tuple(
            sorted(
                {entity.id: entity for entity in matches}.values(), key=lambda x: x.id
            )
        )

    def candidate_rows(
        self,
        *,
        document_id: int,
        entity_type: str,
        surface: str,
        same_scene_ids: set[int],
    ) -> list[dict[str, object]]:
        entities = self.repository.list_for_scope(**self._scope(document_id))
        rows: list[dict[str, object]] = []
        for entity in entities:
            if not self._enabled(entity.id):
                continue
            if entity_type != "other" and entity.entity_type != entity_type:
                continue
            aliases = [
                alias.alias
                for alias in self.repository.aliases_for(entity.id)
                if self._alias_is_usable(alias.id, alias.origin)
            ]
            rows.append(
                {
                    "entity_id": entity.id,
                    "entity_type": entity.entity_type,
                    "canonical_name": self._effective_name(entity),
                    "aliases": aliases,
                    "same_scene": entity.id in same_scene_ids,
                }
            )
        return rows

    def validate_mention_payload(self, payload: Mapping[str, object]) -> None:
        if payload.get("mention_type") not in MENTION_TYPES:
            raise ValueError("MENTION_TYPE_INVALID")
        if payload.get("entity_type_candidate") not in ENTITY_TYPES:
            raise ValueError("ENTITY_TYPE_INVALID")
        for field in ("surface", "canonical_name_candidate"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                raise ValueError("MENTION_FIELD_INVALID")

    def insert_inferred_alias_if_missing(
        self,
        *,
        entity_id: int,
        alias: str,
        alias_kind: str,
        analysis_run_id: int,
        source_mention_id: int,
    ) -> None:
        if not alias or alias_kind in {"title", "role"}:
            return
        entity = self.repository.get(entity_id)
        values = [self._effective_name(entity)] + [
            item.alias for item in self.repository.aliases_for(entity_id)
        ]
        if comparison_key(alias) in {comparison_key(value) for value in values}:
            return
        self.repository.insert_alias(
            entity_id=entity_id,
            alias=alias,
            alias_kind=alias_kind,
            origin="inferred",
            analysis_run_id=analysis_run_id,
            source_mention_id=source_mention_id,
        )

    def _scope(self, document_id: int) -> dict[str, int]:
        row = self._connection.execute(
            "SELECT reference_episode_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        if row[0] is None:
            return {"document_id": document_id}
        work_row = self._connection.execute(
            "SELECT reference_work_id FROM style_reference_episodes WHERE id = ?",
            (row[0],),
        ).fetchone()
        if work_row is None:
            raise ValueError("REFERENCE_EPISODE_NOT_FOUND")
        return {"reference_work_id": cast(int, work_row[0])}

    def _enabled(self, entity_id: int) -> bool:
        row = self._latest_override(entity_id, "entity.enabled")
        if row is None:
            return True
        if row[0] != "set":
            return True
        try:
            return json.loads(cast(str, row[1])) is not False
        except (TypeError, json.JSONDecodeError):
            return False

    def _effective_name(self, entity: EntityRecord) -> str:
        row = self._latest_override(entity.id, "entity.canonical_name")
        if row is None or row[0] != "set" or not isinstance(row[1], str):
            return entity.canonical_name
        try:
            value = json.loads(row[1])
        except json.JSONDecodeError:
            return entity.canonical_name
        return value if isinstance(value, str) and value else entity.canonical_name

    def _latest_override(
        self, subject_id: int, field_path: str
    ) -> tuple[object, object] | None:
        row = self._connection.execute(
            "SELECT operation, value_json FROM style_manual_overrides "
            "WHERE subject_type = 'entity' AND subject_id = ? AND field_path = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (subject_id, field_path),
        ).fetchone()
        return None if row is None else (row[0], row[1])

    def _alias_is_usable(self, alias_id: int, origin: str) -> bool:
        if origin == "manual":
            return True
        row = self._connection.execute(
            "SELECT review_status FROM style_inference_reviews "
            "WHERE subject_type = 'entity_alias' AND subject_id = ? "
            "AND field_path IN ('entity_alias.alias', 'alias') "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (alias_id,),
        ).fetchone()
        return row is not None and row[0] == "confirmed"
