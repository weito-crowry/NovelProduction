from __future__ import annotations

import json
import math
import re

import pytest

from novel_core.document import (
    BlockAttrs,
    NovelBlock,
    NovelDocument,
    new_block_id,
    normalize_document,
    parse_document_json,
    serialize_document_json,
)
from novel_core.errors import DocumentSchemaError

FORMAL_ID = "blk_0123456789abcdef0123456789abcdef"


def document_with_block(**overrides: object) -> NovelDocument:
    values: dict[str, object] = {
        "id": FORMAL_ID,
        "type": "dialogue",
        "html": "「こんにちは」",
        "attrs": BlockAttrs(scene_id=3, speaker_character_id=12),
        "annotations": {"emotions": ["穏やか"], "snack-count": 3},
    }
    values.update(overrides)
    return NovelDocument(
        blocks=(
            NovelBlock(
                id=values["id"],
                type=values["type"],
                html=values["html"],
                attrs=values["attrs"],
                annotations=values["annotations"],
            ),
        )
    )


def assert_schema_error(value: object) -> None:
    with pytest.raises(DocumentSchemaError) as caught:
        parse_document_json(value)  # type: ignore[arg-type]
    assert caught.value.code == "DOCUMENT_SCHEMA_ERROR"


def test_empty_document_and_all_block_types_are_valid() -> None:
    assert (
        parse_document_json('{"schema_version":1,"type":"novel_document","blocks":[]}')
        == NovelDocument()
    )

    blocks = tuple(
        NovelBlock(
            id=f"blk_{index:032x}",
            type=block_type,
            html="" if block_type != "heading" else "見出し",
            attrs=(
                BlockAttrs(heading_level=2) if block_type == "heading" else BlockAttrs()
            ),
        )
        for index, block_type in enumerate(
            (
                "narration",
                "dialogue",
                "thought",
                "description",
                "quote",
                "heading",
                "separator",
                "note",
            ),
            start=1,
        )
    )
    assert normalize_document(NovelDocument(blocks=blocks)).blocks == blocks


def test_schema_round_trip_is_compact_utf8_and_deterministic() -> None:
    document = document_with_block(html="東京\n「急いで！」")
    raw = serialize_document_json(document)

    assert raw == serialize_document_json(parse_document_json(raw))
    assert "東京" in raw
    assert "\\u6771" not in raw
    assert "\n" not in raw
    assert json.loads(raw)["blocks"][0]["id"] == FORMAL_ID
    assert raw.index('"schema_version"') < raw.index('"type"') < raw.index('"blocks"')


def test_new_block_id_is_formal_uuid4_hex() -> None:
    block_id = new_block_id()
    assert re.fullmatch(r"blk_[0-9a-f]{32}", block_id)


def test_null_optional_attrs_are_removed_by_normalization() -> None:
    document = document_with_block(
        attrs=BlockAttrs(scene_id=None, speaker_character_id=12, heading_level=None)
    )
    normalized = normalize_document(document)
    assert normalized.blocks[0].attrs == BlockAttrs(speaker_character_id=12)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "[]",
        '{"schema_version":2,"type":"novel_document","blocks":[]}',
        '{"schema_version":1,"type":"wrong","blocks":[]}',
        '{"schema_version":1,"type":"novel_document","blocks":[],"extra":1}',
        '{"schema_version":1,"type":"novel_document","blocks":[{"id":"bad","type":"dialogue","html":"","attrs":{},"annotations":{}}]}',
        '{"schema_version":1,"type":"novel_document","blocks":[{"id":"blk_0123456789abcdef0123456789abcdef","type":"dialogue","html":"","attrs":{},"annotations":{},"extra":1}]}',
        '{"schema_version":1,"type":"novel_document","blocks":[{"id":"blk_0123456789abcdef0123456789abcdef","type":"dialogue","html":"","attrs":{"unknown":1},"annotations":{}}]}',
        '{"schema_version":1,"type":"novel_document","blocks":[{"id":"blk_0123456789abcdef0123456789abcdef","type":"dialogue","html":"","attrs":{},"annotations":{"emotions":[1]}}]}',
        '{"schema_version":1,"type":"novel_document","blocks":[{"id":"blk_0123456789abcdef0123456789abcdef","type":"dialogue","html":"","attrs":{"scene_id":0},"annotations":{}}]}',
        '{"schema_version":1,"type":"novel_document","blocks":[{"id":"blk_0123456789abcdef0123456789abcdef","type":"heading","html":"","attrs":{"heading_level":2},"annotations":{}}]}',
        '{"schema_version":1,"type":"novel_document","blocks":[{"id":"blk_0123456789abcdef0123456789abcdef","type":"separator","html":"-","attrs":{},"annotations":{}}]}',
        json.dumps(
            {
                "schema_version": 1,
                "type": "novel_document",
                "blocks": [
                    {
                        "id": FORMAL_ID,
                        "type": "dialogue",
                        "html": "",
                        "attrs": {},
                        "annotations": {"not-finite": math.nan},
                    }
                ],
            },
            allow_nan=True,
        ),
    ],
)
def test_invalid_documents_raise_stable_schema_error(raw: object) -> None:
    assert_schema_error(raw)


def test_duplicate_block_ids_are_rejected() -> None:
    raw = json.dumps(
        {
            "schema_version": 1,
            "type": "novel_document",
            "blocks": [
                {
                    "id": FORMAL_ID,
                    "type": "dialogue",
                    "html": "A",
                    "attrs": {},
                    "annotations": {},
                },
                {
                    "id": FORMAL_ID,
                    "type": "dialogue",
                    "html": "B",
                    "attrs": {},
                    "annotations": {},
                },
            ],
        }
    )
    assert_schema_error(raw)
