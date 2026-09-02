from __future__ import annotations

import json
from typing import Any, cast

from novel_core.style_analysis.metrics import METRIC_DEFINITIONS

from novel_api.style_analysis.job_service import DatabaseConnection


class StyleAnalysisDocumentsMixin:
    _connection: DatabaseConnection
    _structure: Any
    _text: Any

    def list_documents(self: Any) -> tuple[dict[str, object], ...]:
        rows = self._connection.execute(
            "SELECT id FROM style_documents ORDER BY id"
        ).fetchall()
        return tuple(
            summary
            for row in rows
            if (summary := self.get_document(int(row[0]))) is not None
        )

    def get_document(self: Any, document_id: int) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT d.id, d.kind, d.current_text_revision_id, "
            "d.current_structure_revision_id, sr.source_kind "
            "FROM style_documents AS d "
            "LEFT JOIN style_structure_revisions AS sr "
            "ON sr.id = d.current_structure_revision_id "
            "WHERE d.id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "document_id": int(row[0]),
            "kind": str(row[1]),
            "current_text_revision_id": row[2],
            "current_structure_revision_id": row[3],
            "current_structure_kind": row[4],
            "analysis_status": self.analysis_status(
                int(row[0]),
                None if row[2] is None else int(row[2]),
                None if row[3] is None else int(row[3]),
            ),
        }

    def list_text_revisions(
        self: Any, document_id: int
    ) -> tuple[dict[str, object], ...]:
        if self.get_document(document_id) is None:
            return ()
        rows = self._connection.execute(
            "SELECT id, document_id, revision_no, source_snapshot_id, "
            "project_draft_id, raw_sha256, canonical_sha256, "
            "normalization_input_fingerprint, normalizer_id, normalizer_version, "
            "metadata_json, created_at FROM style_text_revisions "
            "WHERE document_id = ? ORDER BY revision_no, id",
            (document_id,),
        ).fetchall()
        return tuple(
            {
                "id": int(row[0]),
                "document_id": int(row[1]),
                "revision_no": int(row[2]),
                "source_snapshot_id": row[3],
                "project_draft_id": row[4],
                "raw_sha256": str(row[5]),
                "canonical_sha256": str(row[6]),
                "normalization_input_fingerprint": str(row[7]),
                "normalizer_id": str(row[8]),
                "normalizer_version": int(row[9]),
                "metadata": json.loads(str(row[10])),
                "created_at": str(row[11]),
            }
            for row in rows
        )

    def get_text(self: Any, document_id: int, revision_id: int) -> dict[str, object]:
        revision = self._text.get_text_revision(document_id, revision_id)
        return {
            "id": revision.id,
            "document_id": revision.document_id,
            "revision_no": revision.revision_no,
            "source_snapshot_id": revision.source_snapshot_id,
            "project_draft_id": revision.project_draft_id,
            "raw_text": revision.raw_text,
            "canonical_text": revision.canonical_text,
            "raw_sha256": revision.raw_sha256,
            "canonical_sha256": revision.canonical_sha256,
            "normalization_input_fingerprint": revision.normalization_input_fingerprint,
            "normalizer_id": revision.normalizer_id,
            "normalizer_version": revision.normalizer_version,
            "metadata": json.loads(revision.metadata_json),
            "created_at": revision.created_at,
        }

    def list_structure_revisions(
        self: Any, document_id: int
    ) -> tuple[dict[str, object], ...]:
        if self.get_document(document_id) is None:
            return ()
        rows = self._connection.execute(
            "SELECT sr.id, sr.text_revision_id, sr.revision_no, sr.segmenter_id, "
            "sr.segmenter_version, sr.source_kind, sr.parent_structure_revision_id, "
            "sr.fingerprint, sr.created_at, "
            "(SELECT COUNT(*) FROM style_scenes s "
            "WHERE s.structure_revision_id = sr.id), "
            "(SELECT COUNT(*) FROM style_blocks b "
            "WHERE b.structure_revision_id = sr.id) "
            "FROM style_structure_revisions AS sr "
            "JOIN style_text_revisions AS tr ON tr.id = sr.text_revision_id "
            "WHERE tr.document_id = ? ORDER BY sr.revision_no, sr.id",
            (document_id,),
        ).fetchall()
        return tuple(
            {
                "id": int(row[0]),
                "document_id": document_id,
                "text_revision_id": int(row[1]),
                "revision_no": int(row[2]),
                "segmenter_id": str(row[3]),
                "segmenter_version": int(row[4]),
                "source_kind": str(row[5]),
                "parent_structure_revision_id": row[6],
                "fingerprint": str(row[7]),
                "scene_count": int(row[9]),
                "block_count": int(row[10]),
                "created_at": str(row[8]),
            }
            for row in rows
        )

    def get_structure(
        self: Any, document_id: int, revision_id: int
    ) -> dict[str, object]:
        revision = self._structure.get_structure_revision(document_id, revision_id)
        text_revision = self._text.get_text_revision(
            document_id, revision.text_revision_id
        )
        scenes = self._structure.list_scenes(revision_id)
        blocks = self._structure.list_blocks(revision_id)
        sentences = self._structure.list_sentences(revision_id)
        text = text_revision.canonical_text
        scene_rows = [
            {
                "id": scene.id,
                "structure_revision_id": scene.structure_revision_id,
                "order_index": scene.order_index,
                "start_cp": scene.start_cp,
                "end_cp": scene.end_cp,
                "text": text[scene.start_cp : scene.end_cp],
            }
            for scene in scenes
        ]
        block_rows = [
            {
                "id": block.id,
                "structure_revision_id": block.structure_revision_id,
                "scene_id": block.scene_id,
                "order_index": block.order_index,
                "paragraph_index": block.paragraph_index,
                "block_type": block.block_type,
                "start_cp": block.start_cp,
                "end_cp": block.end_cp,
                "text": text[block.start_cp : block.end_cp],
            }
            for block in blocks
        ]
        sentence_rows = [
            {
                "id": sentence.id,
                "block_id": sentence.block_id,
                "order_index": sentence.order_index,
                "start_cp": sentence.start_cp,
                "end_cp": sentence.end_cp,
                "text": text[sentence.start_cp : sentence.end_cp],
            }
            for sentence in sentences
        ]
        return {
            "id": revision.id,
            "document_id": document_id,
            "text_revision_id": revision.text_revision_id,
            "revision_no": revision.revision_no,
            "segmenter_id": revision.segmenter_id,
            "segmenter_version": revision.segmenter_version,
            "source_kind": revision.source_kind,
            "parent_structure_revision_id": revision.parent_structure_revision_id,
            "fingerprint": revision.fingerprint,
            "created_at": revision.created_at,
            "scene_count": len(scenes),
            "block_count": len(blocks),
            "scenes": scene_rows,
            "blocks": block_rows,
            "sentences": sentence_rows,
        }

    def select_current_structure(
        self: Any, document_id: int, revision_id: int
    ) -> dict[str, object]:
        self._structure.set_current_structure(document_id, revision_id)
        document = self.get_document(document_id)
        if document is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        return cast(dict[str, object], document)

    def split_structure_scene(
        self: Any,
        *,
        document_id: int,
        scene_id: int,
        after_block_id: int,
        expected_structure_revision_id: int,
    ) -> dict[str, object]:
        revision = self._structure.split_scene(
            document_id=document_id,
            scene_id=scene_id,
            after_block_id=after_block_id,
            expected_structure_revision_id=expected_structure_revision_id,
        )
        return cast(dict[str, object], self.get_structure(document_id, revision.id))

    def merge_structure_scenes(
        self: Any,
        *,
        document_id: int,
        scene_id: int,
        next_scene_id: int,
        expected_structure_revision_id: int,
    ) -> dict[str, object]:
        revision = self._structure.merge_scenes(
            document_id=document_id,
            scene_id=scene_id,
            next_scene_id=next_scene_id,
            expected_structure_revision_id=expected_structure_revision_id,
        )
        return cast(dict[str, object], self.get_structure(document_id, revision.id))

    def list_metrics(
        self: Any,
        document_id: int,
        structure_revision_id: int,
        scene_id: int | None = None,
    ) -> dict[str, object]:
        document_row = self._connection.execute(
            "SELECT current_text_revision_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document_row is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        structure = self._structure.get_structure_revision(
            document_id, structure_revision_id
        )
        if scene_id is not None:
            scene_row = self._connection.execute(
                "SELECT 1 FROM style_scenes WHERE id = ? AND structure_revision_id = ?",
                (scene_id, structure_revision_id),
            ).fetchone()
            if scene_row is None:
                raise ValueError("SCENE_STRUCTURE_MISMATCH")
        text_revision_id = int(structure.text_revision_id)
        runs = self._select_runs(
            document_id,
            text_revision_id,
            structure_revision_id,
            ("style-metrics-basic", "style-metrics-semantic"),
        )
        measurements = [
            measurement
            for run in runs
            for measurement in self.list_run_measurements(run.id)
            if scene_id is None
            or (
                measurement["target_type"] == "scene"
                and measurement["target_id"] == scene_id
            )
        ]
        return {
            "document_id": document_id,
            "structure_revision_id": structure_revision_id,
            "analysis_run_ids": [run.id for run in runs],
            "available_metrics": [
                {
                    "name": definition.name,
                    "version": definition.version,
                    "unit": definition.unit,
                    "value_type": definition.value_type,
                    "scope_types": list(definition.scope_types),
                    "group": definition.group,
                    "description": definition.description,
                }
                for definition in METRIC_DEFINITIONS.values()
            ],
            "measurements": measurements,
        }
