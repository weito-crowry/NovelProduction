from __future__ import annotations

import json
import sqlite3
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.fingerprints import JsonObject, fingerprint_json
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


class StyleStructureService:
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
        try:
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
                self._connection.commit()
                return
            self._connection.execute(
                "UPDATE style_documents SET current_structure_revision_id = ? "
                "WHERE id = ?",
                (revision_id, document_id),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def build_automatic_structure(
        self, *, document_id: int, text_revision_id: int
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
        try:
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
                current is not None
                and current[0] == text_revision_id
                and current[1] is None
            ):
                self._connection.execute(
                    "UPDATE style_documents SET current_structure_revision_id = ? "
                    "WHERE id = ?",
                    (revision_id, document_id),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return self.get_structure_revision(document_id, revision_id)

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
