from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.model_contracts import JsonObject as ModelJsonObject
from novel_core.style_analysis.semantic_service import SemanticService
from novel_core.style_analysis.structure_models import BlockRecord
from novel_core.style_analysis.term_service import TermService


class AnalysisStateMixin:
    def _metric_effective_state(
        self: Any, document_id: int, structure_id: int
    ) -> list[dict[str, object]]:
        override_paths = (
            "block.speaker_entity_id",
            "block.semantic_primary",
            "term.novelty",
            "term_mention.sufficient_explanation_annotation_id",
            "mention.entity_id",
        )
        review_paths = (
            "block.speaker",
            "block.semantic_primary",
            "term.novelty",
            "term_mention.explanation",
        )
        override_placeholders = ", ".join("?" for _ in override_paths)
        review_placeholders = ", ".join("?" for _ in review_paths)
        overrides = self.connection.execute(
            "SELECT subject_type, subject_id, field_path, operation, value_json, "
            "structure_revision_id FROM style_manual_overrides "
            "WHERE document_id = ? AND field_path IN (" + override_placeholders + ") "
            "AND (structure_revision_id IS NULL OR structure_revision_id = ?) "
            "ORDER BY subject_type, subject_id, field_path, created_at, id",
            (document_id, *override_paths, structure_id),
        ).fetchall()
        reviews = self.connection.execute(
            "SELECT subject_type, subject_id, field_path, review_status, "
            "analysis_run_id FROM style_inference_reviews "
            "WHERE document_id = ? AND field_path IN (" + review_placeholders + ") "
            "ORDER BY subject_type, subject_id, field_path, created_at, id",
            (document_id, *review_paths),
        ).fetchall()
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
                        "entity_type": entity.entity_type,
                        "canonical_name": entity.canonical_name,
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
                        "('entity_alias.alias', 'alias') "
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
                        "canonical_label": term.canonical_label,
                        "term_type": term.term_type,
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
                        "('term_alias.alias', 'alias') "
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
            "term", scope_field, scope_value
        )
        return [
            {key: sorted(values, key=lambda item: tuple(map(repr, item.values())))}
            for key, values in sorted(state.items())
        ]

    def _scoped_manual_overrides(
        self: Any, subject_type: str, scope_field: str, scope_value: int
    ) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT subject_id, field_path, operation, value_json "
            "FROM style_manual_overrides WHERE subject_type = ? "
            f"AND {scope_field} = ? ORDER BY subject_id, field_path, created_at, id",
            (subject_type, scope_value),
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
        entity_ids: set[int] = set()
        for annotation in self.semantic.repository.list_for_run(resolution_run_id):
            if annotation.annotation_type != "mention.entity_resolution":
                continue
            try:
                value = json.loads(annotation.value_json)
            except json.JSONDecodeError:
                continue
            entity_id = value.get("entity_id") if isinstance(value, dict) else None
            if not isinstance(entity_id, int) or isinstance(entity_id, bool):
                continue
            try:
                mention = self.entities.repository.get_mention(annotation.subject_id)
            except ValueError:
                continue
            if mention.scene_id == scene_id:
                entity_ids.add(entity_id)
        people: list[ModelJsonObject] = []
        for entity_id in sorted(entity_ids):
            try:
                entity = self.entities.repository.get(entity_id)
            except ValueError:
                continue
            if entity.entity_type != "person" or not self.entities._enabled(entity.id):
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
