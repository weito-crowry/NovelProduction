from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.model_contracts import JsonObject as ModelJsonObject
from novel_core.style_analysis.semantic_metric_support import (
    enabled_person,
    resolve_entity_name,
    resolve_entity_type,
    resolve_mention_entity,
    resolve_term_label,
    resolve_term_type,
)
from novel_core.style_analysis.semantic_service import SemanticService
from novel_core.style_analysis.structure_models import BlockRecord
from novel_core.style_analysis.term_service import TermService


class AnalysisStateMixin:
    def _metric_effective_state(
        self: Any, document_id: int, structure_id: int
    ) -> list[dict[str, object]]:
        document_override_paths = (
            "block.speaker_entity_id",
            "block.semantic_primary",
            "term_mention.sufficient_explanation_annotation_id",
        )
        document_review_paths = (
            "block.speaker",
            "block.semantic_primary",
            "term_mention.explanation",
        )
        document_override_placeholders = ", ".join("?" for _ in document_override_paths)
        document_review_placeholders = ", ".join("?" for _ in document_review_paths)
        overrides = self.connection.execute(
            "SELECT subject_type, subject_id, field_path, operation, value_json, "
            "structure_revision_id FROM style_manual_overrides "
            "WHERE document_id = ? AND field_path IN ("
            + document_override_placeholders
            + ") "
            "AND (structure_revision_id IS NULL OR structure_revision_id = ?) "
            "ORDER BY subject_type, subject_id, field_path, created_at, id",
            (document_id, *document_override_paths, structure_id),
        ).fetchall()
        reviews = self.connection.execute(
            "SELECT subject_type, subject_id, field_path, review_status, "
            "analysis_run_id FROM style_inference_reviews "
            "WHERE document_id = ? AND field_path IN ("
            + document_review_placeholders
            + ") ORDER BY subject_type, subject_id, field_path, created_at, id",
            (document_id, *document_review_paths),
        ).fetchall()
        scope_field, scope_value = next(iter(self.terms._scope(document_id).items()))
        term_overrides = self.connection.execute(
            "SELECT subject_type, subject_id, field_path, operation, value_json, "
            "structure_revision_id FROM style_manual_overrides "
            "WHERE subject_type = 'term' AND field_path = 'term.novelty' AND "
            + scope_field
            + " = ? AND (structure_revision_id IS NULL OR structure_revision_id = ?) "
            "ORDER BY subject_type, subject_id, field_path, created_at, id",
            (scope_value, structure_id),
        ).fetchall()
        term_reviews = self.connection.execute(
            "SELECT subject_type, subject_id, field_path, review_status, "
            "analysis_run_id FROM style_inference_reviews "
            "WHERE subject_type = 'term' AND field_path = 'term.novelty' AND "
            + scope_field
            + " = ? ORDER BY subject_type, subject_id, field_path, created_at, id",
            (scope_value,),
        ).fetchall()
        overrides += term_overrides
        reviews += term_reviews
        return [
            {
                "kind": "override",
                "subject_type": str(row[0]),
                "subject_id": int(row[1]),
                "field_path": str(row[2]),
                "operation": str(row[3]),
                "value_json": row[4],
                "structure_revision_id": row[5],
            }
            for row in overrides
        ] + [
            {
                "kind": "review",
                "subject_type": str(row[0]),
                "subject_id": int(row[1]),
                "field_path": str(row[2]),
                "review_status": str(row[3]),
                "analysis_run_id": int(row[4]),
            }
            for row in reviews
        ]

    def _entity_registry_state(self: Any, document_id: int) -> list[dict[str, object]]:
        scope = self.entities._scope(document_id)
        scope_field, scope_value = next(iter(scope.items()))
        state: dict[str, list[dict[str, object]]] = {
            "manual_entities": [],
            "manual_aliases": [],
            "manual_overrides": [],
            "inferred_alias_reviews": [],
        }
        for entity in self.entities.repository.list_for_scope(**scope):
            if entity.origin == "manual":
                state["manual_entities"].append(
                    {
                        "entity_id": entity.id,
                        "entity_type": resolve_entity_type(
                            self.connection, entity.id
                        ).value,
                        "canonical_name": resolve_entity_name(
                            self.connection, entity.id
                        ).value,
                    }
                )
            for alias in self.entities.repository.aliases_for(entity.id):
                if alias.origin == "manual":
                    state["manual_aliases"].append(
                        {
                            "alias_id": alias.id,
                            "entity_id": alias.entity_id,
                            "alias": alias.alias,
                            "alias_kind": alias.alias_kind,
                        }
                    )
                else:
                    review = self.connection.execute(
                        "SELECT review_status, analysis_run_id FROM "
                        "style_inference_reviews WHERE subject_type = 'entity_alias' "
                        "AND subject_id = ? AND field_path IN "
                        "('entity_alias.acceptance') "
                        f"AND {scope_field} = ? "
                        "ORDER BY created_at DESC, id DESC LIMIT 1",
                        (alias.id, scope_value),
                    ).fetchone()
                    if review is not None:
                        state["inferred_alias_reviews"].append(
                            {
                                "alias_id": alias.id,
                                "entity_id": alias.entity_id,
                                "review_status": str(review[0]),
                                "analysis_run_id": int(review[1]),
                            }
                        )
        state["manual_overrides"] = self._scoped_manual_overrides(
            "entity", scope_field, scope_value
        )
        return [
            {key: sorted(values, key=lambda item: tuple(map(repr, item.values())))}
            for key, values in sorted(state.items())
        ]

    def _term_registry_state(self: Any, document_id: int) -> list[dict[str, object]]:
        scope = self.terms._scope(document_id)
        scope_field, scope_value = next(iter(scope.items()))
        state: dict[str, list[dict[str, object]]] = {
            "manual_terms": [],
            "manual_aliases": [],
            "manual_overrides": [],
            "inferred_alias_reviews": [],
        }
        for term in self.terms.repository.list_for_scope(**scope):
            if term.origin == "manual":
                state["manual_terms"].append(
                    {
                        "term_id": term.id,
                        "canonical_label": resolve_term_label(
                            self.connection, term.id
                        ).value,
                        "term_type": resolve_term_type(self.connection, term.id).value,
                    }
                )
            for alias in self.terms.repository.aliases_for(term.id):
                if alias.origin == "manual":
                    state["manual_aliases"].append(
                        {
                            "alias_id": alias.id,
                            "term_id": alias.term_id,
                            "alias": alias.alias,
                        }
                    )
                else:
                    review = self.connection.execute(
                        "SELECT review_status, analysis_run_id FROM "
                        "style_inference_reviews WHERE subject_type = 'term_alias' "
                        "AND subject_id = ? AND field_path IN "
                        "('term_alias.acceptance') "
                        f"AND {scope_field} = ? "
                        "ORDER BY created_at DESC, id DESC LIMIT 1",
                        (alias.id, scope_value),
                    ).fetchone()
                    if review is not None:
                        state["inferred_alias_reviews"].append(
                            {
                                "alias_id": alias.id,
                                "term_id": alias.term_id,
                                "review_status": str(review[0]),
                                "analysis_run_id": int(review[1]),
                            }
                        )
        state["manual_overrides"] = self._scoped_manual_overrides(
            "term",
            scope_field,
            scope_value,
            ("term.enabled", "term.canonical_label", "term.term_type"),
        )
        return [
            {key: sorted(values, key=lambda item: tuple(map(repr, item.values())))}
            for key, values in sorted(state.items())
        ]

    def _scoped_manual_overrides(
        self: Any,
        subject_type: str,
        scope_field: str,
        scope_value: int,
        field_paths: Sequence[str] = (),
    ) -> list[dict[str, object]]:
        field_filter = ""
        parameters: tuple[object, ...] = (subject_type, scope_value)
        if field_paths:
            placeholders = ", ".join("?" for _ in field_paths)
            field_filter = f" AND field_path IN ({placeholders})"
            parameters = (subject_type, scope_value, *field_paths)
        rows = self.connection.execute(
            "SELECT subject_id, field_path, operation, value_json "
            "FROM style_manual_overrides WHERE subject_type = ? "
            f"AND {scope_field} = ?{field_filter} "
            "ORDER BY subject_id, field_path, created_at, id",
            parameters,
        ).fetchall()
        return [
            {
                "subject_id": int(row[0]),
                "field_path": str(row[1]),
                "operation": str(row[2]),
                "value_json": row[3],
            }
            for row in rows
        ]

    def _mention_resolution_state(
        self: Any, document_id: int, structure_id: int, run_id: int
    ) -> list[dict[str, object]]:
        scope = self.entities._scope(document_id)
        scope_field, scope_value = next(iter(scope.items()))
        state: dict[int, dict[str, object]] = {}
        override_rows = self.connection.execute(
            "SELECT subject_id, field_path, operation, value_json "
            "FROM style_manual_overrides WHERE subject_type = 'mention' "
            "AND field_path = 'mention.entity_id' AND structure_revision_id = ? "
            f"AND {scope_field} = ? ORDER BY created_at, id",
            (structure_id, scope_value),
        ).fetchall()
        for row in override_rows:
            state[int(row[0])] = {
                "mention_id": int(row[0]),
                "manual_override": {
                    "field_path": str(row[1]),
                    "operation": str(row[2]),
                    "value_json": row[3],
                },
            }
        review_rows = self.connection.execute(
            "SELECT subject_id, field_path, review_status "
            "FROM style_inference_reviews WHERE subject_type = 'mention' "
            "AND field_path = 'mention.entity_resolution' AND analysis_run_id = ? "
            f"AND {scope_field} = ? ORDER BY created_at, id",
            (run_id, scope_value),
        ).fetchall()
        for row in review_rows:
            item = state.setdefault(int(row[0]), {"mention_id": int(row[0])})
            item["inference_review"] = {
                "field_path": str(row[1]),
                "review_status": str(row[2]),
            }
        return [state[key] for key in sorted(state)]

    def _people_for_scene(
        self: Any, document_id: int, resolution_run_id: int, scene_id: int | None
    ) -> list[ModelJsonObject]:
        if scene_id is None:
            return []
        structure_row = self.connection.execute(
            "SELECT structure_revision_id FROM style_analysis_runs WHERE id = ?",
            (resolution_run_id,),
        ).fetchone()
        if structure_row is None:
            return []
        raw_by_mention = {
            int(annotation.subject_id): (
                annotation.value_json,
                annotation.confidence,
                None,
            )
            for annotation in self.semantic.repository.list_for_run(resolution_run_id)
            if annotation.annotation_type == "mention.entity_resolution"
        }
        entity_ids: set[int] = set()
        mention_rows = self.connection.execute(
            "SELECT id, scene_id FROM style_mentions "
            "WHERE structure_revision_id = ? ORDER BY id",
            (structure_row[0],),
        ).fetchall()
        for mention_id, mention_scene_id in mention_rows:
            entity_id = resolve_mention_entity(
                self.connection,
                int(mention_id),
                resolution_run_id,
                raw_by_mention.get(int(mention_id)),
            ).value
            if not isinstance(entity_id, int) or isinstance(entity_id, bool):
                continue
            if mention_scene_id == scene_id and enabled_person(
                self.connection, entity_id
            ):
                entity_ids.add(entity_id)
        people: list[ModelJsonObject] = []
        for entity_id in sorted(entity_ids):
            try:
                entity = self.entities.repository.get(entity_id)
            except ValueError:
                continue
            people.append(
                {
                    "entity_id": entity.id,
                    "canonical_name": self.entities._effective_name(entity),
                }
            )
        return people

    @staticmethod
    def _block_json(block: BlockRecord, text: str) -> ModelJsonObject:
        return {
            "block_id": block.id,
            "scene_id": block.scene_id,
            "order_index": block.order_index,
            "block_type": block.block_type,
            "text": text[block.start_cp : block.end_cp],
        }

    @staticmethod
    def _block_start(blocks: Sequence[BlockRecord], block_id: int) -> int:
        for block in blocks:
            if block.id == block_id:
                return block.start_cp
        raise ValueError("BLOCK_NOT_FOUND")

    @staticmethod
    def _block_scene(blocks: Sequence[BlockRecord], block_id: int) -> int:
        for block in blocks:
            if block.id == block_id and block.scene_id is not None:
                return block.scene_id
        raise ValueError("SCENE_NOT_FOUND")

    @staticmethod
    def _context(
        blocks: Sequence[ModelJsonObject], block_id: int, before: int, after: int
    ) -> tuple[list[ModelJsonObject], ModelJsonObject, list[ModelJsonObject]]:
        from novel_core.style_analysis.resolver_candidates import build_context_window

        return build_context_window(
            blocks, subject_block_id=block_id, before=before, after=after
        )


class AnalysisStateReader(AnalysisStateMixin):
    """Read-only state adapter shared by execution and current-run resolution."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.entities = EntityService(connection)
        self.terms = TermService(connection)
        self.semantic = SemanticService(connection)
