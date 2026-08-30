from __future__ import annotations

from novel_core.document import (
    BlockAttrs,
    NovelBlock,
    NovelDocument,
    render_context_html,
    render_web_html,
)


def block(
    block_id: str,
    block_type: str,
    html: str,
    *,
    attrs: BlockAttrs | None = None,
    annotations: dict[str, object] | None = None,
) -> NovelBlock:
    return NovelBlock(
        id=f"blk_{block_id * 32}"[:36],
        type=block_type,  # type: ignore[arg-type]
        html=html,
        attrs=attrs or BlockAttrs(),
        annotations=annotations or {},
    )


def test_web_projection_keeps_identity_and_rich_text_but_hides_edit_metadata() -> None:
    document = NovelDocument(
        blocks=(
            block(
                "a",
                "dialogue",
                "<strong>本文</strong>",
                attrs=BlockAttrs(scene_id=3, speaker_character_id=12),
                annotations={"emotions": ["焦り"]},
            ),
            block("b", "note", "制作メモ"),
        )
    )

    web_html = render_web_html(document)
    with_notes = render_web_html(document, include_notes=True)

    assert 'id="blk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' in web_html
    assert "<strong>本文</strong>" in web_html
    assert 'data-np-type="dialogue"' in web_html
    assert "data-np-scene-id" not in web_html
    assert "data-np-speaker-id" not in web_html
    assert "data-ann-" not in web_html
    assert "制作メモ" not in web_html
    assert "制作メモ" in with_notes


def test_context_projection_keeps_context_metadata_without_identity_or_notes() -> None:
    document = NovelDocument(
        blocks=(
            block(
                "a",
                "dialogue",
                "<ruby>東京<rt>とうきょう</rt></ruby>",
                attrs=BlockAttrs(scene_id=3, speaker_character_id=12),
                annotations={"emotions": ["焦り"]},
            ),
            block("b", "note", "制作メモ"),
        )
    )

    result = render_context_html(document)

    assert result.html == (
        '<p data-np-type="dialogue" data-np-scene-id="3" '
        'data-np-speaker-id="12"><ruby>東京<rt>とうきょう</rt></ruby></p>'
    )
    assert ' id="' not in result.html
    assert "data-ann-" not in result.html
    assert "制作メモ" not in result.html
    assert result.selected_block_count == 1
    assert result.visible_text_char_count == 2
    assert result.truncated is False


def test_context_selects_whole_tail_blocks_and_keeps_zero_visible_separator() -> None:
    document = NovelDocument(
        blocks=(
            block("a", "narration", "AAA"),
            block("c", "separator", ""),
            block("b", "narration", "BBB"),
        )
    )

    result = render_context_html(document, max_visible_chars=3)

    assert result.html == '<hr>\n<p data-np-type="narration">BBB</p>'
    assert result.selected_block_count == 2
    assert result.visible_text_char_count == 3
    assert result.truncated is True


def test_context_includes_one_oversized_tail_block_without_cutting_it() -> None:
    document = NovelDocument(blocks=(block("e", "narration", "ABCDE"),))

    result = render_context_html(document, max_visible_chars=3)

    assert result.html == '<p data-np-type="narration">ABCDE</p>'
    assert result.selected_block_count == 1
    assert result.visible_text_char_count == 5
    assert result.truncated is False


def test_context_tail_output_returns_original_order_and_counts_ruby_base_only() -> None:
    document = NovelDocument(
        blocks=(
            block("a", "narration", "A"),
            block("b", "narration", "<ruby>東京<rt>とうきょう</rt></ruby>"),
            block("c", "narration", "C"),
        )
    )

    result = render_context_html(document, max_visible_chars=3)

    assert result.html == (
        '<p data-np-type="narration">'
        "<ruby>東京<rt>とうきょう</rt></ruby></p>\n"
        '<p data-np-type="narration">C</p>'
    )
    assert result.visible_text_char_count == 3
    assert result.selected_block_count == 2
    assert result.truncated is True
