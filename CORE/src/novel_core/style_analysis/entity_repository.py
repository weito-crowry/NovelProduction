from __future__ import annotations

import json
import sqlite3

from novel_core.style_analysis.entity_models import (
    EntityAliasRecord,
    EntityRecord,
    MentionRecord,
)


class EntityRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_inferred(
        self,
        *,
        reference_work_id: int | None,
        document_id: int | None,
        entity_type: str,
        canonical_name: str,
        run_id: int,
    ) -> EntityRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_entities "
            "(reference_work_id, document_id, entity_type, canonical_name, "
            "origin, created_by_run_id) "
            "VALUES (?, ?, ?, ?, 'inferred', ?)",
            (reference_work_id, document_id, entity_type, canonical_name, run_id),
        )
        assert cursor.lastrowid is not None
        return self.get(cursor.lastrowid)

    def get(self, entity_id: int) -> EntityRecord:
        row = self._connection.execute(
            "SELECT id, reference_work_id, document_id, entity_type, canonical_name, "
            "origin, created_by_run_id, created_at FROM style_entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row is None:
            raise ValueError("ENTITY_NOT_FOUND")
        return EntityRecord(*row)

    def list_for_scope(
        self, *, reference_work_id: int | None = None, document_id: int | None = None
    ) -> tuple[EntityRecord, ...]:
        if (reference_work_id is None) == (document_id is None):
            raise ValueError("ENTITY_SCOPE_INVALID")
        field, value = (
            ("reference_work_id", reference_work_id)
            if reference_work_id is not None
            else ("document_id", document_id)
        )
        rows = self._connection.execute(
            "SELECT id, reference_work_id, document_id, entity_type, canonical_name, "
            "origin, created_by_run_id, created_at FROM style_entities "
            f"WHERE {field} = ? ORDER BY id",
            (value,),
        ).fetchall()
        return tuple(EntityRecord(*row) for row in rows)

    def insert_mention(
        self,
        *,
        structure_revision_id: int,
        scene_id: int,
        block_id: int,
        start_cp: int,
        end_cp: int,
        surface: str,
        mention_type: str,
        entity_type_candidate: str,
        canonical_name_candidate: str,
        confidence: float,
        analysis_run_id: int,
    ) -> MentionRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_mentions "
            "(structure_revision_id, scene_id, block_id, start_cp, end_cp, surface, "
            "mention_type, entity_type_candidate, canonical_name_candidate, "
            "confidence, analysis_run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                structure_revision_id,
                scene_id,
                block_id,
                start_cp,
                end_cp,
                surface,
                mention_type,
                entity_type_candidate,
                canonical_name_candidate,
                confidence,
                analysis_run_id,
            ),
        )
        assert cursor.lastrowid is not None
        return self.get_mention(cursor.lastrowid)

    def get_mention(self, mention_id: int) -> MentionRecord:
        row = self._connection.execute(
            "SELECT id, structure_revision_id, scene_id, block_id, start_cp, end_cp, "
            "surface, mention_type, entity_type_candidate, canonical_name_candidate, "
            "confidence, analysis_run_id "
            "FROM style_mentions WHERE id = ?",
            (mention_id,),
        ).fetchone()
        if row is None:
            raise ValueError("MENTION_NOT_FOUND")
        return MentionRecord(*row)

    def list_mentions(self, *, analysis_run_id: int) -> tuple[MentionRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, structure_revision_id, scene_id, block_id, start_cp, end_cp, "
            "surface, mention_type, entity_type_candidate, canonical_name_candidate, "
            "confidence, analysis_run_id "
            "FROM style_mentions WHERE analysis_run_id = ? "
            "ORDER BY scene_id, block_id, start_cp, id",
            (analysis_run_id,),
        ).fetchall()
        return tuple(MentionRecord(*row) for row in rows)

    def insert_alias(
        self,
        *,
        entity_id: int,
        alias: str,
        alias_kind: str,
        origin: str,
        analysis_run_id: int | None,
        source_mention_id: int | None = None,
    ) -> EntityAliasRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_entity_aliases "
            "(entity_id, alias, alias_kind, origin, analysis_run_id, "
            "source_mention_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entity_id, alias, alias_kind, origin, analysis_run_id, source_mention_id),
        )
        assert cursor.lastrowid is not None
        return self.get_alias(cursor.lastrowid)

    def get_alias(self, alias_id: int) -> EntityAliasRecord:
        row = self._connection.execute(
            "SELECT id, entity_id, alias, alias_kind, origin, analysis_run_id, "
            "source_mention_id, created_at FROM style_entity_aliases WHERE id = ?",
            (alias_id,),
        ).fetchone()
        if row is None:
            raise ValueError("ENTITY_ALIAS_NOT_FOUND")
        return EntityAliasRecord(*row)

    def aliases_for(self, entity_id: int) -> tuple[EntityAliasRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, entity_id, alias, alias_kind, origin, analysis_run_id, "
            "source_mention_id, created_at FROM style_entity_aliases "
            "WHERE entity_id = ? ORDER BY alias, id",
            (entity_id,),
        ).fetchall()
        return tuple(EntityAliasRecord(*row) for row in rows)


def json_value(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
