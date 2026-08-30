from __future__ import annotations

import json

import pytest

from novel_core.document import (
    base_visible_text,
    normalize_inline_html,
    parse_inline_html,
    serialize_inline_html,
)
from novel_core.errors import DocumentSchemaError


def test_inline_html_escapes_text_and_preserves_rich_semantics() -> None:
    fragment = (
        '<strong>東京 &amp; "駅"</strong><em>静か</em>'
        '<em data-emphasis="dot">強調</em><br>'
        "<ruby>東京<rt>とうきょう</rt></ruby>"
    )

    assert normalize_inline_html(fragment) == (
        "<strong>東京 &amp; &quot;駅&quot;</strong>"
        '<em>静か</em><em data-emphasis="dot">強調</em>'
        "<br><ruby>東京<rt>とうきょう</rt></ruby>"
    )
    assert base_visible_text(fragment) == '東京 & "駅"静か強調\n東京'


def test_inline_parser_round_trip_uses_decoded_text() -> None:
    parsed = parse_inline_html("A &lt; B &amp; 日本")
    assert serialize_inline_html(parsed) == "A &lt; B &amp; 日本"


def test_inline_normalization_uses_lf_line_endings() -> None:
    assert normalize_inline_html("A\r\nB\rC") == "A\nB\nC"


@pytest.mark.parametrize(
    "fragment",
    [
        "<span>本文</span>",
        '<strong class="x">本文</strong>',
        '<a href="/">本文</a>',
        "<script>alert(1)</script>",
        "<!-- comment -->本文",
        "<!DOCTYPE html>本文",
        '<?xml version="1.0"?>本文',
        "<strong>本文",
        "<strong>本文</em>",
        "<br></br>",
        "<rt>よみ</rt>",
        "<ruby>東京</ruby>",
        "<ruby>東京<rt>よみ</rt><rt>ふり</rt></ruby>",
        "<ruby><strong>東京</strong><rt>よみ</rt></ruby>",
        "<ruby>東京<rt><em>よみ</em></rt></ruby>",
        "<ruby>東京<rt>よみ</rt>余分</ruby>",
        "<ruby><br><rt>よみ</rt></ruby>",
    ],
)
def test_invalid_inline_html_is_rejected(fragment: str) -> None:
    with pytest.raises(DocumentSchemaError) as caught:
        normalize_inline_html(fragment)
    assert caught.value.code == "DOCUMENT_SCHEMA_ERROR"


def test_schema_uses_the_restricted_inline_validator() -> None:
    raw = json.dumps(
        {
            "schema_version": 1,
            "type": "novel_document",
            "blocks": [
                {
                    "id": "blk_0123456789abcdef0123456789abcdef",
                    "type": "dialogue",
                    "html": "<span>禁止</span>",
                    "attrs": {},
                    "annotations": {},
                }
            ],
        }
    )
    with pytest.raises(DocumentSchemaError):
        from novel_core.document import parse_document_json

        parse_document_json(raw)
