from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import cast

from novel_core.style_analysis.entity_models import (
    ALIAS_KINDS,
    ENTITY_TYPES,
    MENTION_TYPES,
    EntityAliasRecord,
    EntityRecord,
)
from novel_core.style_analysis.entity_repository import EntityRepository
from novel_core.style_analysis.resolver_candidates import exact_key


class EntityService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.repository = EntityRepository(connection)

    def create_manual_entity(
        self,
        *,
        reference_work_id: int | None,
        document_id: int | None,
        entity_type: str,
        canonical_name: str,
    ) -> EntityRecord:
        if (reference_work_id is None) == (document_id is None):
            raise ValueError("ENTITY_SCOPE_INVALID")
        if entity_type not in ENTITY_TYPES:
            raise ValueError("ENTITY_TYPE_INVALID")
        if document_id is not None:
            row = self._connection.execute(
                "SELECT reference_episode_id FROM style_documents WHERE id=?",
                (document_id,),
            ).fetchone()
            if row is None:
                raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
            if row[0] is not None:
                raise ValueError("ENTITY_SCOPE_INVALID")
        name = canonical_name.strip() if isinstance(canonical_name, str) else ""
        if not 1 <= len(name) <= 200:
            raise ValueError("ENTITY_NAME_INVALID")
        with self._write_transaction():
            cursor = self._connection.execute(
                "INSERT INTO style_entities "
                "(reference_work_id, document_id, entity_type, canonical_name, origin) "
                "VALUES (?, ?, ?, ?, 'manual')",
                (reference_work_id, document_id, entity_type, name),
            )
            assert cursor.lastrowid is not None
            return self.repository.get(cursor.lastrowid)

    def create_manual_alias(
        self, *, entity_id: int, alias: str, alias_kind: str
    ) -> EntityAliasRecord:
        if alias_kind not in ALIAS_KINDS:
            raise ValueError("ALIAS_KIND_INVALID")
        normalized = alias.strip() if isinstance(alias, str) else ""
        if not 1 <= len(normalized) <= 200:
            raise ValueError("ALIAS_INVALID")
        self.repository.get(entity_id)
        existing = self._connection.execute(
            "SELECT id FROM style_entity_aliases "
            "WHERE entity_id=? AND alias=? AND alias_kind=? AND origin='manual' "
            "ORDER BY id LIMIT 1",
            (entity_id, normalized, alias_kind),
        ).fetchone()
        if existing is not None:
            return self.repository.get_alias(int(existing[0]))
        with self._write_transaction():
            return self.repository.insert_alias(
                entity_id=entity_id,
                alias=normalized,
                alias_kind=alias_kind,
                origin="manual",
                analysis_run_id=None,
            )

    def link_character(
        self, *, document_id: int, style_entity_id: int, project_character_id: int
    ) -> dict[str, int]:
        document = self._connection.execute(
            "SELECT project_work_id, reference_episode_id "
            "FROM style_documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if document is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        if document[1] is not None or document[0] is None:
            raise ValueError("CHARACTER_LINK_DOCUMENT_INVALID")
        entity = self._connection.execute(
            "SELECT document_id, reference_work_id FROM style_entities WHERE id=?",
            (style_entity_id,),
        ).fetchone()
        if entity is None:
            raise ValueError("ENTITY_NOT_FOUND")
        if (entity[0], entity[1]) != (document_id, None):
            raise ValueError("CHARACTER_LINK_SCOPE_INVALID")
        from novel_core.style_analysis.semantic_metric_support import enabled_person

        if not enabled_person(self._connection, style_entity_id):
            raise ValueError("CHARACTER_LINK_ENTITY_INVALID")
        character = self._connection.execute(
            "SELECT work_id FROM characters WHERE id=?", (project_character_id,)
        ).fetchone()
        if character is None:
            raise ValueError("CHARACTER_NOT_FOUND")
        if int(character[0]) != int(document[0]):
            raise ValueError("CHARACTER_LINK_SCOPE_INVALID")
        try:
            with self._write_transaction():
                self._connection.execute(
                    "INSERT INTO style_entity_character_links "
                    "(document_id, style_entity_id, project_character_id) "
                    "VALUES (?, ?, ?)",
                    (document_id, style_entity_id, project_character_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("CHARACTER_LINK_CONFLICT") from exc
        return {
            "document_id": document_id,
            "style_entity_id": style_entity_id,
            "project_character_id": project_character_id,
        }

    def unlink_character(self, *, document_id: int, project_character_id: int) -> bool:
        with self._write_transaction():
            cursor = self._connection.execute(
                "DELETE FROM style_entity_character_links "
                "WHERE document_id=? AND project_character_id=?",
                (document_id, project_character_id),
            )
        return cursor.rowcount > 0

    def exact_matches(
        self, *, document_id: int, surface: str
    ) -> tuple[EntityRecord, ...]:
        scope = self._scope(document_id)
        entities = self.repository.list_for_scope(**scope)
        matches: list[EntityRecord] = []
        key = exact_key(surface)
        for entity in entities:
            if not self._enabled(entity.id):
                continue
            if exact_key(self._effective_name(entity)) == key:
                matches.append(entity)
                continue
            for alias in self.repository.aliases_for(entity.id):
                if not self._alias_is_usable(alias.id, alias.origin):
                    continue
                if exact_key(alias.alias) == key:
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
        normalized_alias = alias.strip() if isinstance(alias, str) else ""
        if not normalized_alias or alias_kind == "pronoun":
            return
        entity = self.repository.get(entity_id)
        values = [self._effective_name(entity).strip()] + [
            item.alias for item in self.repository.aliases_for(entity_id)
        ]
        if exact_key(normalized_alias) in {
            exact_key(value.strip()) for value in values
        }:
            return
        self.repository.insert_alias(
            entity_id=entity_id,
            alias=normalized_alias,
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
        from novel_core.style_analysis.semantic_metric_support import latest_override

        row = latest_override(self._connection, "entity", subject_id, field_path)
        return None if row is None else (row[1], row[2])

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

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        savepoint = "style_entity_write"
        owns_transaction = not self._connection.in_transaction
        if owns_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        else:
            self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield
            if owns_transaction:
                self._connection.commit()
            else:
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            else:
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
