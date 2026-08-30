from __future__ import annotations

from pathlib import Path

import pytest

from novel_core.document import (
    AnnotationProjection,
    AuthoringBlockInput,
    BlockAttrs,
    NovelBlock,
    NovelDocument,
    parse_authoring_html,
    serialize_authoring_html,
)
from novel_core.errors import DocumentSchemaError

FORMAL_ID = "blk_0123456789abcdef0123456789abcdef"


def test_untyped_paragraph_does_not_guess_existing_type() -> None:
    parsed = parse_authoring_html('<p id="correlation-1">本文</p>')

    assert parsed == (
        AuthoringBlockInput(
            supplied_id="correlation-1",
            type_hint=None,
            html="本文",
            attrs={},
            annotations={},
            remove_annotations=(),
        ),
    )


def test_forced_tags_and_explicit_structural_metadata_are_parsed() -> None:
    parsed = parse_authoring_html(
        '<p data-np-type="dialogue" data-np-scene-id="3" '
        'data-np-speaker-id="12">台詞</p>'
        '<blockquote id="quote-1">引用</blockquote>'
        '<h2 id="heading-1">章</h2><hr id="separator-1">'
    )

    assert parsed[0].type_hint == "dialogue"
    assert parsed[0].attrs == {"scene_id": 3, "speaker_character_id": 12}
    assert parsed[1].type_hint == "quote"
    assert parsed[2].type_hint == "heading"
    assert parsed[2].attrs == {"heading_level": 2}
    assert parsed[3].type_hint == "separator"
    assert parsed[3].html == ""


def test_structural_attribute_omission_and_clear_are_distinct() -> None:
    parsed = parse_authoring_html(
        '<p id="clear" data-np-scene-id="" data-np-speaker-id="12">本文</p>'
        '<p id="inherit">続き</p>'
    )

    assert parsed[0].attrs == {"scene_id": None, "speaker_character_id": 12}
    assert parsed[1].attrs == {}


def test_annotations_use_string_namespace_and_emotions_codec() -> None:
    parsed = parse_authoring_html(
        '<p data-ann-emotions="[&quot;焦り&quot;]" '
        'data-ann-snack-count="3" '
        'data-np-remove-annotations="[&quot;old-key&quot;]">本文</p>'
    )

    assert parsed[0].annotations == {"emotions": ["焦り"], "snack-count": "3"}
    assert parsed[0].remove_annotations == ("old-key",)


@pytest.mark.parametrize(
    "attribute_value",
    ["foo DATA-NP-BAR", "foo DATA-ANN-BAR baz"],
)
def test_namespace_spelling_ignores_reserved_tokens_inside_attribute_values(
    attribute_value: str,
) -> None:
    parsed = parse_authoring_html(f'<p data-ann-note="{attribute_value}">本文</p>')

    assert parsed[0].annotations == {"note": attribute_value}


@pytest.mark.parametrize("attribute_name", ["DATA-NP-TYPE", "DATA-ANN-FOO"])
def test_namespace_spelling_rejects_mixed_case_attribute_names(
    attribute_name: str,
) -> None:
    with pytest.raises(DocumentSchemaError):
        parse_authoring_html(f'<p {attribute_name}="x">本文</p>')


@pytest.mark.parametrize(
    "html",
    [
        '<p id="">本文</p>',
        '<p id="same">A</p><p id="same">B</p>',
        '<p data-np-type="">本文</p>',
        '<p data-np-type="heading">本文</p>',
        '<blockquote data-np-type="quote">引用</blockquote>',
        '<p data-np-unknown="x">本文</p>',
        '<p class="x">本文</p>',
        '<p data-np-scene-id="0">本文</p>',
        '<p data-np-speaker-id="1.2">本文</p>',
        '<p data-ann-Upper="x">本文</p>',
        '<p data-ann-emotions="not-json">本文</p>',
        '<p data-ann-emotions="[1]">本文</p>',
        '<p data-np-remove-annotations="[&quot;old&quot;,&quot;old&quot;]">本文</p>',
        "before<p>本文</p>",
        "<p><p>nested</p></p>",
    ],
)
def test_invalid_authoring_html_is_rejected(html: str) -> None:
    with pytest.raises(DocumentSchemaError) as caught:
        parse_authoring_html(html)
    assert caught.value.code == "DOCUMENT_SCHEMA_ERROR"


def test_projection_modes_and_complex_annotation_non_loss_policy() -> None:
    document = NovelDocument(
        blocks=(
            NovelBlock(
                id=FORMAL_ID,
                type="note",
                html="制作メモ",
                annotations={
                    "emotions": ["注意"],
                    "snack-count": "3",
                    "complex": {"raw": True},
                },
            ),
        )
    )

    none_html = serialize_authoring_html(document, AnnotationProjection("none"))
    selected_html = serialize_authoring_html(
        document,
        AnnotationProjection("selected", ("emotions", "snack-count", "complex")),
    )
    all_html = serialize_authoring_html(document, AnnotationProjection("all"))

    assert "data-ann-" not in none_html
    assert 'data-ann-emotions="[&quot;注意&quot;]"' in selected_html
    assert 'data-ann-snack-count="3"' in selected_html
    assert "data-ann-complex" not in selected_html
    assert selected_html == all_html
    assert document.blocks[0].annotations["complex"] == {"raw": True}


def test_canonical_authoring_round_trip_preserves_projected_semantics() -> None:
    document = NovelDocument(
        blocks=(
            NovelBlock(
                id=FORMAL_ID,
                type="dialogue",
                html="<strong>急いで</strong>",
                attrs=BlockAttrs(scene_id=3, speaker_character_id=12),
                annotations={"emotions": ["焦り"], "snack-count": "3"},
            ),
            NovelBlock(
                id="blk_abcdefabcdefabcdefabcdefabcdefab",
                type="heading",
                html="第一章",
                attrs=BlockAttrs(heading_level=1),
            ),
            NovelBlock(
                id="blk_11111111111111111111111111111111",
                type="quote",
                html="引用",
            ),
            NovelBlock(
                id="blk_22222222222222222222222222222222",
                type="separator",
                html="",
            ),
            NovelBlock(
                id="blk_33333333333333333333333333333333",
                type="note",
                html="メモ",
            ),
        )
    )

    rendered = serialize_authoring_html(document, AnnotationProjection("all"))
    parsed = parse_authoring_html(rendered)

    assert tuple(item.supplied_id for item in parsed) == tuple(
        block.id for block in document.blocks
    )
    assert tuple(item.type_hint for item in parsed) == (
        "dialogue",
        "heading",
        "quote",
        "separator",
        "note",
    )
    assert parsed[0].html == document.blocks[0].html
    assert parsed[0].attrs == {"scene_id": 3, "speaker_character_id": 12}
    assert parsed[0].annotations == {"emotions": ["焦り"], "snack-count": "3"}
    assert parsed[1].attrs == {"heading_level": 1}
    assert parsed[3].html == ""


def test_emotions_empty_array_is_valid() -> None:
    parsed = parse_authoring_html('<p data-ann-emotions="[]">本文</p>')
    assert parsed[0].annotations == {"emotions": []}


def test_shared_tiptap_fixture_is_accepted_with_expected_semantics() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "phase_e_tiptap_roundtrip.html"
    )
    parsed = parse_authoring_html(fixture_path.read_text(encoding="utf-8"))

    assert tuple(item.supplied_id for item in parsed) == (
        "blk_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "blk_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "blk_cccccccccccccccccccccccccccccccc",
        "blk_dddddddddddddddddddddddddddddddd",
        "blk_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    )
    assert parsed[0].type_hint == "dialogue"
    assert parsed[0].attrs == {"scene_id": 3, "speaker_character_id": 12}
    assert parsed[0].annotations == {"emotions": ["焦り"]}
    assert parsed[0].html == (
        "<strong>急いで</strong><em>斜体</em>"
        '<em data-emphasis="dot">傍点</em>'
        "<ruby>東京<rt>とうきょう</rt></ruby><br>！"
    )
    assert tuple(item.type_hint for item in parsed[1:]) == (
        "note",
        "heading",
        "separator",
        "quote",
    )
