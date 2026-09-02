from __future__ import annotations

import json
import sqlite3
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.fingerprints import JsonObject, fingerprint_json
from novel_core.style_analysis.manual_structure_editor import (
    ManualStructureEditingMixin,
)
from novel_core.style_analysis.segmentation import build_automatic_structure
from novel_core.style_analysis.structure_models import (
    BlockRecord,
    SceneRecord,
    SentenceRecord,
    StructureRevisionRecord,
)
from novel_core.style_analysis.text_service import StyleTextService

_STRUCTURE_REVISION_COLUMNS = (
    "sr.id, sr.text_revision_id, sr.revision_no, sr.segmenter_id, "
    "sr.segmenter_version, sr.source_kind, sr.parent_structure_revision_id, "
    "sr.fingerprint, sr.created_at"
)


class StyleStructureService(ManualStructureEditingMixin):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._text_service = StyleTextService(connection)

    def get_structure_revision(
        self, document_id: int, revision_id: int
    ) -> StructureRevisionRecord:
        row = self._connection.execute(
            f"SELECT {_STRUCTURE_REVISION_COLUMNS} "
            "FROM style_structure_revisions AS sr "
            "JOIN style_text_revisions AS tr ON tr.id = sr.text_revision_id "
            "WHERE tr.document_id = ? AND sr.id = ?",
            (document_id, revision_id),
        ).fetchone()
        if row is None:
            raise ValidationError("STRUCTURE_REVISION_DOCUMENT_MISMATCH")
        return StructureRevisionRecord(*row)

    def set_current_structure(self, document_id: int, revision_id: int) -> None:
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            document = self._text_service.get_document(document_id)
            if document is None:
                raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
            structure = self.get_structure_revision(document_id, revision_id)
            if (
                document.current_text_revision_id is None
                or structure.text_revision_id != document.current_text_revision_id
            ):
                raise ValidationError("CURRENT_STRUCTURE_TEXT_MISMATCH")
            if document.current_structure_revision_id == revision_id:
                if owns_transaction:
                    self._connection.commit()
                return
            self._connection.execute(
                "UPDATE style_documents SET current_structure_revision_id = ? "
                "WHERE id = ?",
                (revision_id, document_id),
            )
            if owns_transaction:
                self._connection.commit()
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            raise

    def set_current_structure_if_current_text(
        self, document_id: int, revision_id: int
    ) -> bool:
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            document = self._text_service.get_document(document_id)
            if document is None:
                raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
            structure = self.get_structure_revision(document_id, revision_id)
            if (
                document.current_text_revision_id is None
                or structure.text_revision_id != document.current_text_revision_id
            ):
                if owns_transaction:
                    self._connection.commit()
                return False
            self._connection.execute(
                "UPDATE style_documents SET current_structure_revision_id = ? "
                "WHERE id = ?",
                (revision_id, document_id),
            )
            if owns_transaction:
                self._connection.commit()
            return True
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            raise

    def build_automatic_structure(
        self,
        *,
        document_id: int,
        text_revision_id: int,
        set_current: bool = True,
    ) -> StructureRevisionRecord:
        document = self._text_service.get_document(document_id)
        if document is None:
            raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
        text_revision = self._text_service.get_text_revision(
            document_id, text_revision_id
        )
        hints = _canonical_scene_hints(text_revision.metadata_json)
        segmenter_id = "canonical-fiction-structure"
        segmenter_version = 1
        fingerprint = fingerprint_json(
            cast(
                JsonObject,
                {
                    "canonical_sha256": text_revision.canonical_sha256,
                    "segmenter_id": segmenter_id,
                    "segmenter_version": segmenter_version,
                    "config": {},
                    "structure_hints": {"scene_break_offsets_cp": hints},
                },
            )
        )
        draft = build_automatic_structure(text_revision.canonical_text, hints)
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT id FROM style_structure_revisions "
                "WHERE text_revision_id = ? AND fingerprint = ?",
                (text_revision_id, fingerprint),
            ).fetchone()
            if existing is not None:
                revision_id = cast(int, existing[0])
            else:
                revision_no = self._connection.execute(
                    "SELECT COALESCE(MAX(revision_no), 0) + 1 "
                    "FROM style_structure_revisions WHERE text_revision_id = ?",
                    (text_revision_id,),
                ).fetchone()[0]
                cursor = self._connection.execute(
                    "INSERT INTO style_structure_revisions "
                    "(text_revision_id, revision_no, segmenter_id, "
                    "segmenter_version, source_kind, fingerprint) "
                    "VALUES (?, ?, ?, ?, 'automatic', ?)",
                    (
                        text_revision_id,
                        revision_no,
                        segmenter_id,
                        segmenter_version,
                        fingerprint,
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError(
                        "automatic structure insert did not return an id"
                    )
                revision_id = cursor.lastrowid
                scene_ids: list[int] = []
                for scene in draft.scenes:
                    scene_cursor = self._connection.execute(
                        "INSERT INTO style_scenes "
                        "(structure_revision_id, order_index, start_cp, end_cp) "
                        "VALUES (?, ?, ?, ?)",
                        (revision_id, len(scene_ids) + 1, scene.start_cp, scene.end_cp),
                    )
                    if scene_cursor.lastrowid is None:
                        raise RuntimeError("scene insert did not return an id")
                    scene_ids.append(scene_cursor.lastrowid)
                for order_index, block in enumerate(draft.blocks, start=1):
                    scene_id = (
                        scene_ids[block.scene_index]
                        if block.scene_index is not None
                        else None
                    )
                    block_cursor = self._connection.execute(
                        "INSERT INTO style_blocks "
                        "(structure_revision_id, scene_id, order_index, "
                        "paragraph_index, block_type, start_cp, end_cp) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            revision_id,
                            scene_id,
                            order_index,
                            block.paragraph_index,
                            block.block_type,
                            block.start_cp,
                            block.end_cp,
                        ),
                    )
                    if block_cursor.lastrowid is None:
                        raise RuntimeError("block insert did not return an id")
                    for sentence_order, sentence in enumerate(block.sentences, start=1):
                        self._connection.execute(
                            "INSERT INTO style_sentences "
                            "(block_id, order_index, start_cp, end_cp) "
                            "VALUES (?, ?, ?, ?)",
                            (
                                block_cursor.lastrowid,
                                sentence_order,
                                sentence.start_cp,
                                sentence.end_cp,
                            ),
                        )
            current = self._connection.execute(
                "SELECT current_text_revision_id, current_structure_revision_id "
                "FROM style_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if (
                set_current
                and current is not None
                and current[0] == text_revision_id
                and current[1] is None
            ):
                self._connection.execute(
                    "UPDATE style_documents SET current_structure_revision_id = ? "
                    "WHERE id = ?",
                    (revision_id, document_id),
                )
            if owns_transaction:
                self._connection.commit()
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            raise
        return self.get_structure_revision(document_id, revision_id)

    def materialize_semantic_structure(
        self,
        *,
        document_id: int,
        text_revision_id: int,
        parent_structure_revision_id: int,
        boundary_analysis_run_id: int,
        auto_apply_threshold: float,
    ) -> StructureRevisionRecord:
        parent = self.get_structure_revision(document_id, parent_structure_revision_id)
        if parent.text_revision_id != text_revision_id:
            raise ValidationError("STRUCTURE_TEXT_REVISION_MISMATCH")
        if parent.source_kind != "automatic":
            raise ValidationError("SEMANTIC_PARENT_NOT_AUTOMATIC")
        runs = AnalysisRunRepository(self._connection)
        boundary_run = runs.get_run(boundary_analysis_run_id)
        if boundary_run is None:
            raise ValidationError("BOUNDARY_RUN_NOT_FOUND")
        if (
            boundary_run.analyzer_id != "scene-boundary-detector"
            or boundary_run.text_revision_id != text_revision_id
            or boundary_run.structure_revision_id != parent_structure_revision_id
        ):
            raise ValidationError("BOUNDARY_PARENT_MISMATCH")

        blocks = self.list_blocks(parent_structure_revision_id)
        block_by_id = {block.id: block for block in blocks}
        content_blocks = [block for block in blocks if block.scene_id is not None]
        content_position = {
            block.id: index for index, block in enumerate(content_blocks)
        }
        existing_after: set[int] = set()
        for prior_block, following in zip(
            content_blocks, content_blocks[1:], strict=False
        ):
            if prior_block.scene_id != following.scene_id:
                existing_after.add(prior_block.id)

        applied: set[int] = set()
        rows = self._connection.execute(
            "SELECT subject_type, subject_id, value_json, confidence "
            "FROM style_annotations WHERE annotation_type = ? "
            "AND analysis_run_id = ? ORDER BY id",
            ("scene_boundary_candidate", boundary_analysis_run_id),
        ).fetchall()
        for subject_type, subject_id, value_json, confidence in rows:
            if subject_type != "block" or not isinstance(subject_id, int):
                continue
            if (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or confidence < auto_apply_threshold
            ):
                continue
            try:
                value = json.loads(cast(str, value_json))
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            if value.get("base_structure_revision_id") != parent_structure_revision_id:
                continue
            after_block_id = subject_id
            if (
                not isinstance(after_block_id, int)
                or isinstance(after_block_id, bool)
                or after_block_id not in block_by_id
                or after_block_id in existing_after
            ):
                continue
            position = content_position.get(after_block_id)
            if position is None or position + 1 >= len(content_blocks):
                continue
            if (
                content_blocks[position].scene_id
                != content_blocks[position + 1].scene_id
            ):
                continue
            applied.add(after_block_id)

        if not applied:
            return parent

        fingerprint = fingerprint_json(
            cast(
                JsonObject,
                {
                    "parent_fingerprint": parent.fingerprint,
                    "boundary_run_fingerprint": boundary_run.fingerprint,
                    "sorted_applied_after_block_ids": sorted(applied),
                    "config": {"scene_boundary_auto_apply": auto_apply_threshold},
                },
            )
        )
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT id FROM style_structure_revisions "
                "WHERE text_revision_id = ? AND fingerprint = ?",
                (text_revision_id, fingerprint),
            ).fetchone()
            if existing is not None:
                semantic_id = cast(int, existing[0])
            else:
                next_revision = self._connection.execute(
                    "SELECT COALESCE(MAX(revision_no), 0) + 1 "
                    "FROM style_structure_revisions WHERE text_revision_id = ?",
                    (text_revision_id,),
                ).fetchone()
                assert next_revision is not None
                cursor = self._connection.execute(
                    "INSERT INTO style_structure_revisions "
                    "(text_revision_id, revision_no, segmenter_id, "
                    "segmenter_version, source_kind, parent_structure_revision_id, "
                    "fingerprint) VALUES (?, ?, ?, ?, 'semantic', ?, ?)",
                    (
                        text_revision_id,
                        cast(int, next_revision[0]),
                        "canonical-fiction-structure",
                        1,
                        parent_structure_revision_id,
                        fingerprint,
                    ),
                )
                assert cursor.lastrowid is not None
                semantic_id = cursor.lastrowid
                groups: list[list[BlockRecord]] = []
                current_group: list[BlockRecord] = []
                group_previous: BlockRecord | None = None
                for block in content_blocks:
                    if (
                        group_previous is None
                        or block.scene_id != group_previous.scene_id
                        or group_previous.id in applied
                    ):
                        if current_group:
                            groups.append(current_group)
                        current_group = []
                    current_group.append(block)
                    group_previous = block
                if current_group:
                    groups.append(current_group)

                scene_by_block: dict[int, int] = {}
                for order_index, group in enumerate(groups, start=1):
                    scene_cursor = self._connection.execute(
                        "INSERT INTO style_scenes "
                        "(structure_revision_id, order_index, start_cp, end_cp) "
                        "VALUES (?, ?, ?, ?)",
                        (semantic_id, order_index, group[0].start_cp, group[-1].end_cp),
                    )
                    assert scene_cursor.lastrowid is not None
                    for block in group:
                        scene_by_block[block.id] = scene_cursor.lastrowid

                for block in blocks:
                    block_cursor = self._connection.execute(
                        "INSERT INTO style_blocks "
                        "(structure_revision_id, scene_id, order_index, "
                        "paragraph_index, block_type, start_cp, end_cp) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            semantic_id,
                            scene_by_block.get(block.id),
                            block.order_index,
                            block.paragraph_index,
                            block.block_type,
                            block.start_cp,
                            block.end_cp,
                        ),
                    )
                    assert block_cursor.lastrowid is not None
                    sentence_rows = self._connection.execute(
                        "SELECT order_index, start_cp, end_cp FROM style_sentences "
                        "WHERE block_id = ? ORDER BY order_index",
                        (block.id,),
                    ).fetchall()
                    for sentence_order, start_cp, end_cp in sentence_rows:
                        self._connection.execute(
                            "INSERT INTO style_sentences "
                            "(block_id, order_index, start_cp, end_cp) "
                            "VALUES (?, ?, ?, ?)",
                            (block_cursor.lastrowid, sentence_order, start_cp, end_cp),
                        )
            runs.add_structure_analysis_source(semantic_id, boundary_analysis_run_id)
            if owns_transaction:
                self._connection.commit()
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            raise
        return self.get_structure_revision(document_id, semantic_id)

    def list_scenes(self, structure_revision_id: int) -> tuple[SceneRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, structure_revision_id, order_index, start_cp, end_cp "
            "FROM style_scenes WHERE structure_revision_id = ? ORDER BY order_index",
            (structure_revision_id,),
        ).fetchall()
        return tuple(SceneRecord(*row) for row in rows)

    def list_blocks(self, structure_revision_id: int) -> tuple[BlockRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, structure_revision_id, scene_id, order_index, "
            "paragraph_index, block_type, start_cp, end_cp FROM style_blocks "
            "WHERE structure_revision_id = ? ORDER BY order_index",
            (structure_revision_id,),
        ).fetchall()
        return tuple(BlockRecord(*row) for row in rows)

    def list_sentences(self, structure_revision_id: int) -> tuple[SentenceRecord, ...]:
        rows = self._connection.execute(
            "SELECT ss.id, ss.block_id, ss.order_index, ss.start_cp, ss.end_cp "
            "FROM style_sentences AS ss JOIN style_blocks AS sb "
            "ON sb.id = ss.block_id WHERE sb.structure_revision_id = ? "
            "ORDER BY sb.order_index, ss.order_index",
            (structure_revision_id,),
        ).fetchall()
        return tuple(SentenceRecord(*row) for row in rows)


def _canonical_scene_hints(metadata_json: str) -> list[int]:
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        raise ValidationError("TEXT_METADATA_INVALID") from exc
    structure_hints = metadata.get("structure_hints", {})
    hints = structure_hints.get("scene_break_offsets_cp", [])
    if not isinstance(hints, list) or any(
        not isinstance(offset, int) or isinstance(offset, bool) for offset in hints
    ):
        raise ValidationError("STRUCTURE_HINTS_INVALID")
    return sorted(set(hints))
