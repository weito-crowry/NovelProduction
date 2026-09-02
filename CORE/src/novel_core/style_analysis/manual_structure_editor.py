from __future__ import annotations

import sqlite3
from typing import Any, cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.fingerprints import JsonObject, fingerprint_json
from novel_core.style_analysis.structure_models import (
    BlockRecord,
    SceneRecord,
    StructureRevisionRecord,
)


class ManualStructureEditingMixin:
    _connection: sqlite3.Connection

    def split_scene(
        self: Any,
        *,
        document_id: int,
        scene_id: int,
        after_block_id: int,
        expected_structure_revision_id: int,
    ) -> StructureRevisionRecord:
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            parent, scene_groups, blocks = self._manual_edit_parent(
                document_id, expected_structure_revision_id
            )
            group_index = next(
                (
                    index
                    for index, (scene, group_blocks) in enumerate(scene_groups)
                    if scene.id == scene_id
                    and any(
                        candidate.id == after_block_id for candidate in group_blocks
                    )
                ),
                None,
            )
            if group_index is None:
                raise ValidationError("MANUAL_SPLIT_BLOCK_INVALID")
            source_scene, group_blocks = scene_groups[group_index]
            split_index = next(
                index
                for index, candidate in enumerate(group_blocks)
                if candidate.id == after_block_id
            )
            if split_index + 1 >= len(group_blocks):
                raise ValidationError("MANUAL_SPLIT_BLOCK_INVALID")
            scene_groups[group_index : group_index + 1] = [
                (source_scene, group_blocks[: split_index + 1]),
                (source_scene, group_blocks[split_index + 1 :]),
            ]
            revision = self._materialize_manual_structure(
                document_id=document_id,
                parent=parent,
                scene_groups=scene_groups,
                operation="split",
                operation_args={"after_block_id": after_block_id},
                blocks=blocks,
            )
            if owns_transaction:
                self._connection.commit()
            return cast(StructureRevisionRecord, revision)
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            raise

    def merge_scenes(
        self: Any,
        *,
        document_id: int,
        scene_id: int,
        next_scene_id: int,
        expected_structure_revision_id: int,
    ) -> StructureRevisionRecord:
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            parent, scene_groups, blocks = self._manual_edit_parent(
                document_id, expected_structure_revision_id
            )
            scene_index = next(
                (
                    index
                    for index, (scene, _) in enumerate(scene_groups)
                    if scene.id == scene_id
                ),
                None,
            )
            next_index = next(
                (
                    index
                    for index, (scene, _) in enumerate(scene_groups)
                    if scene.id == next_scene_id
                ),
                None,
            )
            if scene_index is None or next_index != scene_index + 1:
                raise ValidationError("MANUAL_MERGE_SCENES_INVALID")
            first_scene, first_blocks = scene_groups[scene_index]
            _, following_blocks = scene_groups[next_index]
            scene_groups[scene_index : next_index + 1] = [
                (first_scene, first_blocks + following_blocks)
            ]
            revision = self._materialize_manual_structure(
                document_id=document_id,
                parent=parent,
                scene_groups=scene_groups,
                operation="merge",
                operation_args={"scene_id": scene_id, "next_scene_id": next_scene_id},
                blocks=blocks,
            )
            if owns_transaction:
                self._connection.commit()
            return cast(StructureRevisionRecord, revision)
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            raise

    def _manual_edit_parent(
        self: Any, document_id: int, expected_structure_revision_id: int
    ) -> tuple[
        StructureRevisionRecord,
        list[tuple[SceneRecord, list[BlockRecord]]],
        list[BlockRecord],
    ]:
        document = self._text_service.get_document(document_id)
        if document is None:
            raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
        if document.current_structure_revision_id != expected_structure_revision_id:
            raise ValidationError("STRUCTURE_REVISION_NOT_CURRENT")
        parent = self.get_structure_revision(
            document_id, expected_structure_revision_id
        )
        scenes = list(self.list_scenes(parent.id))
        blocks = list(self.list_blocks(parent.id))
        scene_groups = [
            (
                scene,
                [block for block in blocks if block.scene_id == scene.id],
            )
            for scene in scenes
        ]
        return parent, scene_groups, blocks

    def _materialize_manual_structure(
        self: Any,
        *,
        document_id: int,
        parent: StructureRevisionRecord,
        scene_groups: list[tuple[SceneRecord, list[BlockRecord]]],
        operation: str,
        operation_args: dict[str, int],
        blocks: list[BlockRecord],
    ) -> StructureRevisionRecord:
        fingerprint = fingerprint_json(
            cast(
                JsonObject,
                {
                    "parent_fingerprint": parent.fingerprint,
                    "operation": operation,
                    "operation_args": operation_args,
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
                (parent.text_revision_id, fingerprint),
            ).fetchone()
            if existing is not None:
                revision_id = cast(int, existing[0])
            else:
                next_revision = self._connection.execute(
                    "SELECT COALESCE(MAX(revision_no), 0) + 1 "
                    "FROM style_structure_revisions WHERE text_revision_id = ?",
                    (parent.text_revision_id,),
                ).fetchone()
                assert next_revision is not None
                cursor = self._connection.execute(
                    "INSERT INTO style_structure_revisions "
                    "(text_revision_id, revision_no, segmenter_id, "
                    "segmenter_version, source_kind, parent_structure_revision_id, "
                    "fingerprint) VALUES (?, ?, ?, ?, 'manual', ?, ?)",
                    (
                        parent.text_revision_id,
                        int(next_revision[0]),
                        "canonical-fiction-structure",
                        1,
                        parent.id,
                        fingerprint,
                    ),
                )
                assert cursor.lastrowid is not None
                revision_id = cursor.lastrowid
                new_scene_by_block: dict[int, int] = {}
                for order_index, (source_scene, group_blocks) in enumerate(
                    scene_groups, start=1
                ):
                    start_cp = (
                        group_blocks[0].start_cp
                        if group_blocks
                        else source_scene.start_cp
                    )
                    end_cp = (
                        group_blocks[-1].end_cp if group_blocks else source_scene.end_cp
                    )
                    scene_cursor = self._connection.execute(
                        "INSERT INTO style_scenes "
                        "(structure_revision_id, order_index, start_cp, end_cp) "
                        "VALUES (?, ?, ?, ?)",
                        (revision_id, order_index, start_cp, end_cp),
                    )
                    assert scene_cursor.lastrowid is not None
                    for block in group_blocks:
                        new_scene_by_block[block.id] = scene_cursor.lastrowid
                for block in blocks:
                    block_cursor = self._connection.execute(
                        "INSERT INTO style_blocks "
                        "(structure_revision_id, scene_id, order_index, "
                        "paragraph_index, block_type, start_cp, end_cp) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            revision_id,
                            new_scene_by_block.get(block.id),
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
        return cast(
            StructureRevisionRecord,
            self.get_structure_revision(document_id, revision_id),
        )
