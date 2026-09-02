from __future__ import annotations

import hashlib

from test_style_analysis_sources import open_test_database

from novel_core.style_analysis.source_models import SourceEpisodeInput, SourceWorkInput
from novel_core.style_analysis.source_repository import StyleSourceRepository
from novel_core.style_analysis.structure_service import StyleStructureService


def _create_document(connection) -> int:
    payload = b"manual-structure"
    result = StyleSourceRepository(connection).insert_import(
        source_type="text",
        external_work_id=hashlib.sha256(payload).hexdigest(),
        original_filename="manual.txt",
        adapter_id="test",
        adapter_version=1,
        payload=payload,
        media_type="text/plain",
        source_metadata={},
        work=SourceWorkInput(
            title="Manual",
            author_name=None,
            metadata={},
            episodes=(
                SourceEpisodeInput(
                    external_episode_id="1",
                    title="Episode",
                    order_index=1,
                    raw_text="第一文。\n\n第二文。\n\n第三文。",
                    metadata={"scene_break_offsets_raw": []},
                ),
            ),
        ),
    )
    connection.commit()
    episode = StyleSourceRepository(connection).list_reference_episodes(result.work.id)[
        0
    ]
    assert episode.style_document_id is not None
    return episode.style_document_id


def test_manual_split_merge_creates_append_only_revisions_and_reuses_fingerprints(
    tmp_path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        document_id = _create_document(connection)
        service = StyleStructureService(connection)
        automatic = service.build_automatic_structure(
            document_id=document_id,
            text_revision_id=connection.execute(
                "SELECT current_text_revision_id FROM style_documents WHERE id = ?",
                (document_id,),
            ).fetchone()[0],
        )
        blocks = service.list_blocks(automatic.id)
        assert len(blocks) == 3
        assert blocks[0].scene_id is not None
        scene_id = blocks[0].scene_id

        split = service.split_scene(
            document_id=document_id,
            scene_id=scene_id,
            after_block_id=blocks[0].id,
            expected_structure_revision_id=automatic.id,
        )
        assert split.source_kind == "manual"
        assert split.segmenter_id == "canonical-fiction-structure"
        assert split.segmenter_version == 1
        assert split.parent_structure_revision_id == automatic.id
        assert len(service.list_scenes(split.id)) == 2
        assert connection.execute(
            "SELECT current_structure_revision_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone() == (split.id,)

        service.set_current_structure(document_id, automatic.id)
        split_again = service.split_scene(
            document_id=document_id,
            scene_id=scene_id,
            after_block_id=blocks[0].id,
            expected_structure_revision_id=automatic.id,
        )
        assert split_again.id == split.id

        scenes = service.list_scenes(split.id)
        merged = service.merge_scenes(
            document_id=document_id,
            scene_id=scenes[0].id,
            next_scene_id=scenes[1].id,
            expected_structure_revision_id=split.id,
        )
        assert merged.source_kind == "manual"
        assert merged.segmenter_id == "canonical-fiction-structure"
        assert merged.segmenter_version == 1
        assert merged.parent_structure_revision_id == split.id
        assert len(service.list_scenes(merged.id)) == 1
    finally:
        connection.close()
