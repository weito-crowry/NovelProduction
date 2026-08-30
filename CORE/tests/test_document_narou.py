from __future__ import annotations

import pytest

from novel_core.document import BlockAttrs, NovelBlock, NovelDocument, export_document


def make_block(block_id: str, block_type: str, html: str) -> NovelBlock:
    return NovelBlock(
        id=f"blk_{block_id * 32}",
        type=block_type,  # type: ignore[arg-type]
        html=html,
    )


def test_narou_renders_prose_formatting_ruby_and_block_separation() -> None:
    document = NovelDocument(
        blocks=(
            make_block(
                "a",
                "narration",
                "<strong>太字</strong><em>斜体</em>"
                '<em data-emphasis="dot">傍点</em><br>次',
            ),
            make_block("b", "heading", "章"),
            make_block("c", "quote", "<ruby>東京<rt>とうきょう</rt></ruby>"),
            make_block("d", "separator", ""),
        )
    )
    document = NovelDocument(
        blocks=(
            document.blocks[0],
            NovelBlock(
                id="blk_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                type="heading",
                html="章",
                attrs=BlockAttrs(heading_level=2),
            ),
            document.blocks[2],
            document.blocks[3],
        )
    )

    result = export_document(document, "narou")

    assert result.format == "narou"
    assert result.media_type == "text/plain"
    assert result.suggested_filename is None
    assert (
        result.content == "太字斜体傍点\n次\n\n章\n\n｜東京《とうきょう》\n\n＊　＊　＊"
    )
    assert result.warnings == ()


def test_narou_excludes_notes_metadata_and_block_ids() -> None:
    document = NovelDocument(
        blocks=(
            NovelBlock(
                id="blk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                type="note",
                html="制作メモ",
                attrs=BlockAttrs(scene_id=3, speaker_character_id=12),
                annotations={"emotions": ["内緒"]},
            ),
            make_block("b", "narration", "本文"),
        )
    )

    result = export_document(document, "narou")

    assert result.content == "本文"
    assert "制作メモ" not in result.content
    assert "blk_" not in result.content


@pytest.mark.parametrize(
    "ruby",
    [
        "<ruby>ABCDEFGHIJK<rt>よみ</rt></ruby>",
        "<ruby>東京<rt>よみよみよみよみよみよみよみよみよみよみよみ</rt></ruby>",
    ],
)
def test_narou_degrades_out_of_range_ruby_with_warning(ruby: str) -> None:
    document = NovelDocument(blocks=(make_block("c", "narration", ruby),))

    result = export_document(document, "narou")

    assert "東京" in result.content or "ABCDEFGHIJK" in result.content
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "NAROU_RUBY_DEGRADED"
    assert result.warnings[0].block_id == document.blocks[0].id


def test_unknown_export_format_is_explicitly_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported export format: markdown"):
        export_document(NovelDocument(), "markdown")
