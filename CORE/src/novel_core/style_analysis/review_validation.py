from __future__ import annotations

import json
import sqlite3
from typing import cast

from novel_core.style_analysis.review_support import (
    ALIAS_KINDS,
    BLOCK_PRIMARY_LABELS,
    ENTITY_TYPES,
    NOVELTY_VALUES,
    POV_MODES,
    SCENE_FUNCTIONS,
    SCENE_INFORMATION_LOADS,
    SCENE_INTERACTIONS,
    SCENE_PACES,
    SCENE_TONES,
    STRUCTURE_SUBJECTS,
    TERM_TYPES,
    SubjectInfo,
)
from novel_core.style_analysis.semantic_metric_support import enabled_person


class ReviewValidationMixin:
    _connection: sqlite3.Connection

    def _subject_info(self, subject_type: str, subject_id: int) -> SubjectInfo:
        queries = {
            "structure_revision": (
                "SELECT tr.document_id, NULL, sr.id, NULL, NULL, NULL "
                "FROM style_structure_revisions sr JOIN style_text_revisions tr "
                "ON tr.id = sr.text_revision_id WHERE sr.id = ?"
            ),
            "scene": (
                "SELECT tr.document_id, NULL, s.structure_revision_id, NULL, NULL, "
                "NULL "
                "FROM style_scenes s JOIN style_structure_revisions sr "
                "ON sr.id=s.structure_revision_id JOIN style_text_revisions tr "
                "ON tr.id=sr.text_revision_id WHERE s.id=?"
            ),
            "block": (
                "SELECT tr.document_id, NULL, b.structure_revision_id, NULL, NULL, "
                "b.id "
                "FROM style_blocks b JOIN style_structure_revisions sr "
                "ON sr.id=b.structure_revision_id JOIN style_text_revisions tr "
                "ON tr.id=sr.text_revision_id WHERE b.id=?"
            ),
            "mention": (
                "SELECT tr.document_id, NULL, m.structure_revision_id, m.start_cp, "
                "m.end_cp, m.block_id FROM style_mentions m "
                "JOIN style_structure_revisions sr "
                "ON sr.id=m.structure_revision_id JOIN style_text_revisions tr "
                "ON tr.id=sr.text_revision_id WHERE m.id=?"
            ),
            "term_mention": (
                "SELECT tr.document_id, NULL, m.structure_revision_id, m.start_cp, "
                "m.end_cp, m.block_id FROM style_term_mentions m "
                "JOIN style_structure_revisions sr "
                "ON sr.id=m.structure_revision_id JOIN style_text_revisions tr "
                "ON tr.id=sr.text_revision_id WHERE m.id=?"
            ),
            "entity": (
                "SELECT document_id, reference_work_id, NULL, NULL, NULL, NULL "
                "FROM style_entities WHERE id = ?"
            ),
            "term": (
                "SELECT document_id, reference_work_id, NULL, NULL, NULL, NULL "
                "FROM style_terms WHERE id = ?"
            ),
        }
        query = queries.get(subject_type)
        if query is None:
            raise ValueError("REVIEW_SUBJECT_TYPE_INVALID")
        row = self._connection.execute(query, (subject_id,)).fetchone()
        if row is None:
            raise ValueError("REVIEW_SUBJECT_NOT_FOUND")
        if subject_type in STRUCTURE_SUBJECTS | {"structure_revision"}:
            scope_field, scope_value = self._document_scope(int(row[0]))
            scoped_document_id = scope_value if scope_field == "document_id" else None
            scoped_reference_work_id = (
                scope_value if scope_field == "reference_work_id" else None
            )
        else:
            scoped_document_id = cast(int | None, row[0])
            scoped_reference_work_id = cast(int | None, row[1])
        return SubjectInfo(
            scoped_document_id,
            scoped_reference_work_id,
            cast(int | None, row[2]),
            cast(int | None, row[3]),
            cast(int | None, row[4]),
            cast(int | None, row[5]),
        )

    def _validate_requested_scope(
        self,
        info: SubjectInfo,
        document_id: int | None,
        reference_work_id: int | None,
    ) -> None:
        requested = tuple(
            (field, value)
            for field, value in (
                ("document_id", document_id),
                ("reference_work_id", reference_work_id),
            )
            if value is not None
        )
        if len(requested) > 1 or (requested and requested[0] != info.scope):
            raise ValueError("REVIEW_SCOPE_MISMATCH")

    def _validate_override_lineage(
        self,
        subject_type: str,
        info: SubjectInfo,
        structure_revision_id: int | None,
    ) -> None:
        if subject_type in STRUCTURE_SUBJECTS:
            if (
                structure_revision_id is None
                or structure_revision_id != info.structure_revision_id
            ):
                raise ValueError("STRUCTURE_REVISION_INVALID")
        elif structure_revision_id is not None:
            row = self._connection.execute(
                "SELECT tr.document_id FROM style_structure_revisions sr "
                "JOIN style_text_revisions tr ON tr.id=sr.text_revision_id "
                "WHERE sr.id=?",
                (structure_revision_id,),
            ).fetchone()
            if row is None or self._document_scope(int(row[0])) != info.scope:
                raise ValueError("STRUCTURE_REVISION_INVALID")

    def _validate_run_scope(self, run_id: int, info: SubjectInfo) -> int:
        row = self._connection.execute(
            "SELECT document_id FROM style_analysis_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise ValueError("ANALYSIS_RUN_NOT_FOUND")
        run_document_id = int(row[0])
        if self._document_scope(run_document_id) != info.scope:
            raise ValueError("ANALYSIS_RUN_SCOPE_INVALID")
        return run_document_id

    def _document_scope(self, document_id: int) -> tuple[str, int]:
        row = self._connection.execute(
            "SELECT reference_episode_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        if row[0] is None:
            return "document_id", document_id
        work = self._connection.execute(
            "SELECT reference_work_id FROM style_reference_episodes WHERE id = ?",
            (row[0],),
        ).fetchone()
        if work is None:
            raise ValueError("REFERENCE_EPISODE_NOT_FOUND")
        return "reference_work_id", int(work[0])

    def _validate_alias_review(
        self, subject_type: str, alias_id: int, analysis_run_id: int, info: SubjectInfo
    ) -> None:
        table = (
            "style_entity_aliases"
            if subject_type == "entity_alias"
            else "style_term_aliases"
        )
        columns = "origin, analysis_run_id"
        if subject_type == "entity_alias":
            columns += ", alias_kind"
        row = self._connection.execute(
            f"SELECT {columns} FROM {table} WHERE id = ?", (alias_id,)
        ).fetchone()
        if row is None or row[0] != "inferred" or row[1] != analysis_run_id:
            raise ValueError("INFERENCE_REVIEW_SOURCE_NOT_FOUND")
        if subject_type == "entity_alias" and row[2] not in ALIAS_KINDS:
            raise ValueError("INFERENCE_REVIEW_SOURCE_NOT_FOUND")
        parent_type = "entity" if subject_type == "entity_alias" else "term"
        parent_column = "entity_id" if parent_type == "entity" else "term_id"
        parent = self._connection.execute(
            f"SELECT {parent_column} FROM {table} WHERE id = ?", (alias_id,)
        ).fetchone()
        if (
            parent is None
            or self._subject_info(parent_type, int(parent[0])).scope != info.scope
        ):
            raise ValueError("INFERENCE_REVIEW_SCOPE_INVALID")

    def _validate_annotation_value(
        self,
        annotation_type: str,
        value_json: object,
        info: SubjectInfo,
        subject_type: str,
        subject_id: int,
    ) -> None:
        try:
            value = json.loads(cast(str, value_json))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID") from exc
        if not isinstance(value, dict):
            raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        if annotation_type == "mention.entity_resolution":
            entity_id = value.get("entity_id")
            if entity_id is not None and (
                not isinstance(entity_id, int)
                or isinstance(entity_id, bool)
                or not self._entity_in_scope(entity_id, info)
            ):
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        elif annotation_type == "speaker":
            entity_id = value.get("speaker_entity_id")
            if entity_id is not None and (
                not isinstance(entity_id, int)
                or isinstance(entity_id, bool)
                or not self._entity_in_scope(entity_id, info)
            ):
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        elif annotation_type == "block.semantic_primary":
            if value.get("label") not in BLOCK_PRIMARY_LABELS:
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        elif annotation_type == "term.novelty":
            if value.get("value") not in NOVELTY_VALUES:
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        elif annotation_type == "term_explanation":
            if value.get("completeness") not in {
                "sufficient",
                "insufficient",
                "unclear",
            }:
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        elif annotation_type in {"scene.function", "scene.tone"}:
            labels = value.get("labels")
            allowed = (
                SCENE_FUNCTIONS if annotation_type == "scene.function" else SCENE_TONES
            )
            if (
                not isinstance(labels, list)
                or any(
                    not isinstance(item, dict) or item.get("label") not in allowed
                    for item in labels
                )
                or len({item.get("label") for item in labels if isinstance(item, dict)})
                != len(labels)
            ):
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        elif annotation_type in {
            "scene.pace",
            "scene.information_load",
            "scene.interaction",
        }:
            allowed = {
                "scene.pace": SCENE_PACES,
                "scene.information_load": SCENE_INFORMATION_LOADS,
                "scene.interaction": SCENE_INTERACTIONS,
            }[annotation_type]
            if value.get("label") not in allowed:
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
        elif annotation_type == "scene.pov":
            if value.get("pov_mode") not in POV_MODES:
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")
            entity_id = value.get("pov_entity_id")
            if entity_id is not None and (
                not isinstance(entity_id, int)
                or isinstance(entity_id, bool)
                or not self._entity_in_scope(entity_id, info)
            ):
                raise ValueError("INFERENCE_REVIEW_SOURCE_INVALID")

    def _validate_value(
        self,
        subject_type: str,
        field_path: str,
        value: object,
        info: SubjectInfo,
        subject_id: int,
    ) -> None:
        if field_path.endswith(".enabled"):
            if not isinstance(value, bool):
                raise ValueError("OVERRIDE_VALUE_INVALID")
            return
        if field_path in {"entity.canonical_name", "term.canonical_label"}:
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
                raise ValueError("OVERRIDE_VALUE_INVALID")
            return
        enum_values: frozenset[str] | None = {
            "entity.entity_type": ENTITY_TYPES,
            "term.term_type": TERM_TYPES,
            "term.novelty": NOVELTY_VALUES,
            "block.semantic_primary": BLOCK_PRIMARY_LABELS,
            "scene.pace": SCENE_PACES,
            "scene.information_load": SCENE_INFORMATION_LOADS,
            "scene.interaction": SCENE_INTERACTIONS,
            "scene.pov_mode": POV_MODES,
        }.get(field_path)
        if enum_values is not None:
            if not isinstance(value, str) or value not in enum_values:
                raise ValueError("OVERRIDE_VALUE_INVALID")
            return
        if field_path in {"scene.function", "scene.tone"}:
            allowed = SCENE_FUNCTIONS if field_path == "scene.function" else SCENE_TONES
            if (
                not isinstance(value, list)
                or not value
                or any(
                    not isinstance(item, str) or item not in allowed for item in value
                )
                or len(set(value)) != len(value)
                or ("unclear" in value and len(value) > 1)
            ):
                raise ValueError("OVERRIDE_VALUE_INVALID")
            return
        if field_path.endswith("_entity_id") or field_path.endswith(".entity_id"):
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not self._entity_in_scope(value, info)
            ):
                raise ValueError("OVERRIDE_VALUE_INVALID")
            if (
                value is not None
                and field_path in {"block.speaker_entity_id", "scene.pov_entity_id"}
                and not enabled_person(self._connection, value)
            ):
                raise ValueError("OVERRIDE_VALUE_INVALID")
            return
        if field_path == "term_mention.sufficient_explanation_annotation_id":
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not self._valid_explanation(value, info, subject_id)
            ):
                raise ValueError("OVERRIDE_VALUE_INVALID")
            return
        raise ValueError("OVERRIDE_VALUE_INVALID")

    def _entity_in_scope(self, entity_id: int, info: SubjectInfo) -> bool:
        row = self._connection.execute(
            "SELECT document_id, reference_work_id FROM style_entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        return row is not None and (row[0], row[1]) == (
            info.document_id,
            info.reference_work_id,
        )

    def _valid_explanation(
        self, annotation_id: int, info: SubjectInfo, term_mention_id: int
    ) -> bool:
        row = self._connection.execute(
            "SELECT a.subject_type, a.subject_id, tr.document_id, "
            "r.structure_revision_id "
            "FROM style_annotations a JOIN style_analysis_runs r "
            "ON r.id=a.analysis_run_id "
            "JOIN style_text_revisions tr ON tr.id=r.text_revision_id "
            "WHERE a.id=? AND a.annotation_type='term_explanation'",
            (annotation_id,),
        ).fetchone()
        return (
            row is not None
            and row[0] == "term_mention"
            and int(row[1]) == term_mention_id
            and self._document_scope(int(row[2])) == info.scope
            and (
                info.structure_revision_id is None
                or int(row[3]) == info.structure_revision_id
            )
        )

    def _has_active_override(
        self, subject_type: str, subject_id: int, field_path: str
    ) -> bool:
        rows = self._connection.execute(
            "SELECT operation FROM style_manual_overrides "
            "WHERE subject_type=? AND subject_id=? AND field_path=? "
            "ORDER BY created_at, id",
            (subject_type, subject_id, field_path),
        ).fetchall()
        active: list[str] = []
        for (operation,) in rows:
            if operation in {"set", "clear"}:
                active.append(str(operation))
            elif active:
                active.pop()
        return bool(active)
