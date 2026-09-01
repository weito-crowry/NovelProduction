from __future__ import annotations

import hashlib
from pathlib import Path

from test_style_analysis_sources import open_test_database

from novel_core.style_analysis.segmentation import build_automatic_structure
from novel_core.style_analysis.source_models import SourceEpisodeInput, SourceWorkInput
from novel_core.style_analysis.source_repository import StyleSourceRepository
from novel_core.style_analysis.structure_service import StyleStructureService


def test_automatic_structure_splits_dialogue_and_sentences_without_monologue() -> None:
    draft = build_automatic_structure(
        "第一章\n\n彼は言った。「こんにちは。元気？」と笑った。\n\n---\n\n次の場面。",
        [],
    )
    assert [block.block_type for block in draft.blocks] == [
        "heading",
        "narration",
        "dialogue",
        "narration",
        "separator",
        "narration",
    ]
    assert all(block.block_type != "monologue" for block in draft.blocks)
    dialogue = draft.blocks[2]
    assert len(dialogue.sentences) == 2
    assert len(draft.scenes) == 2
    assert draft.blocks[0].paragraph_index == 1
    assert draft.blocks[1].paragraph_index == 2


def test_automatic_structure_applies_only_exact_block_boundary_hints() -> None:
    text = "第一文。\n\n第二文。\n\n第三文。"
    exact = len("第一文。")
    draft = build_automatic_structure(text, [exact, exact + 1])
    assert len(draft.scenes) == 2
    assert "scene_break_hint_not_on_block_boundary" in draft.warnings
    assert draft.scenes[0].end_cp == exact


def test_boundary_hint_without_following_text_is_dropped_with_warning() -> None:
    draft = build_automatic_structure("第一文。\n\n---", [4])
    assert len(draft.scenes) == 1
    assert "scene_break_hint_not_on_block_boundary" in draft.warnings


def test_sentence_splitter_keeps_closing_quote_on_sentence() -> None:
    draft = build_automatic_structure("「一。」\n\n「二」", [])
    dialogue_sentences = [
        sentence
        for block in draft.blocks
        if block.block_type == "dialogue"
        for sentence in block.sentences
    ]
    assert len(dialogue_sentences) == 2
    assert draft.blocks[0].end_cp == dialogue_sentences[0].end_cp


def test_quoted_symbol_only_paragraphs_take_dialogue_precedence() -> None:
    draft = build_automatic_structure("「……」\n\n「……", [])
    assert [block.block_type for block in draft.blocks] == ["dialogue", "dialogue"]
    assert "unmatched_dialogue_quote" in draft.warnings


def test_automatic_structure_is_persisted_and_reused(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path)
    try:
        repository = StyleSourceRepository(connection)
        result = repository.insert_import(
            source_type="text",
            external_work_id=hashlib.sha256(b"ignored").hexdigest(),
            original_filename="book.txt",
            adapter_id="test",
            adapter_version=1,
            payload=b"ignored",
            media_type="text/plain",
            source_metadata={},
            work=SourceWorkInput(
                title="Reference",
                author_name=None,
                metadata={},
                episodes=(
                    SourceEpisodeInput(
                        external_episode_id="1",
                        title="Episode",
                        order_index=1,
                        raw_text="ignored",
                        metadata={"scene_break_offsets_raw": []},
                    ),
                ),
            ),
        )
        connection.commit()
        episode = repository.list_reference_episodes(result.work.id)[0]
        assert episode.style_document_id is not None
        assert episode.current_text_revision_id is not None
        first = StyleStructureService(connection).build_automatic_structure(
            document_id=episode.style_document_id,
            text_revision_id=episode.current_text_revision_id,
        )
        second = StyleStructureService(connection).build_automatic_structure(
            document_id=episode.style_document_id,
            text_revision_id=episode.current_text_revision_id,
        )
        assert first.id == second.id
        assert connection.execute(
            "SELECT COUNT(*) FROM style_structure_revisions"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM style_blocks WHERE structure_revision_id = ?",
            (first.id,),
        ).fetchone() == (1,)
        connection.execute(
            "INSERT INTO style_structure_revisions "
            "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
            "source_kind, fingerprint) VALUES (?, 2, ?, 1, 'manual', ?)",
            (episode.current_text_revision_id, "manual-test", "c" * 64),
        )
        connection.commit()
        manual_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        StyleStructureService(connection).set_current_structure(
            episode.style_document_id, manual_id
        )
        reused_with_manual_current = StyleStructureService(
            connection
        ).build_automatic_structure(
            document_id=episode.style_document_id,
            text_revision_id=episode.current_text_revision_id,
        )
        assert reused_with_manual_current.id == first.id
        document = connection.execute(
            "SELECT current_structure_revision_id FROM style_documents WHERE id = ?",
            (episode.style_document_id,),
        ).fetchone()
        assert document == (manual_id,)
    finally:
        connection.close()
