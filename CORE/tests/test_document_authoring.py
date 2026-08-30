from __future__ import annotations

import pytest

from novel_core.document.authoring import (
    import_plain_text,
    resolve_authoring,
)
from novel_core.document.model import BlockAttrs, NovelBlock, NovelDocument
from novel_core.errors import DocumentSchemaError, ValidationError


def _document(*blocks: NovelBlock) -> NovelDocument:
    return NovelDocument(blocks=tuple(blocks))


def _block(
    block_id: str,
    html: str,
    *,
    block_type: str = "narration",
    scene_id: int | None = None,
    speaker_character_id: int | None = None,
    heading_level: int | None = None,
    annotations: dict[str, object] | None = None,
) -> NovelBlock:
    return NovelBlock(
        id=block_id,
        type=block_type,  # type: ignore[arg-type]
        html=html,
        attrs=BlockAttrs(
            scene_id=scene_id,
            speaker_character_id=speaker_character_id,
            heading_level=heading_level,
        ),
        annotations={} if annotations is None else annotations,
    )


def test_plain_import_normalizes_line_endings_and_splits_only_blank_runs() -> None:
    document = import_plain_text("\r\n  一行  \r二行\n\n \t\n三行\n")

    assert [block.type for block in document.blocks] == ["narration", "narration"]
    assert [block.html for block in document.blocks] == ["  一行  <br>二行", "三行"]
    assert all(block.id.startswith("blk_") for block in document.blocks)


def test_plain_import_empty_or_surrounding_blank_text_creates_empty_document() -> None:
    assert import_plain_text(" \r\n\t\n ").blocks == ()
    assert import_plain_text("").blocks == ()


def test_html_is_a_complete_snapshot_and_reconciles_parent_and_correlation_ids() -> (
    None
):
    parent = _document(
        _block("blk_11111111111111111111111111111111", "A", scene_id=3),
        _block(
            "blk_22222222222222222222222222222222",
            "B",
            block_type="dialogue",
            speaker_character_id=8,
            annotations={"emotions": ["焦り"], "complex": {"n": 1}},
        ),
        _block("blk_33333333333333333333333333333333", "C"),
    )

    result = resolve_authoring(
        parent,
        '<p id="blk_11111111111111111111111111111111">A2</p><p id="new-b">D</p>',
        None,
    )

    assert [block.html for block in result.document.blocks] == ["A2", "D"]
    assert result.document.blocks[0].attrs.scene_id == 3
    assert result.document.blocks[1].type == "narration"
    assert result.id_map.keys() == {"new-b"}
    assert result.document.blocks[1].id == result.id_map["new-b"]


def test_deleted_historical_id_is_not_reused_by_normal_authoring() -> None:
    parent = _document(_block("blk_11111111111111111111111111111111", "A"))

    result = resolve_authoring(
        parent,
        '<p id="blk_22222222222222222222222222222222">new</p>',
        None,
    )

    assert result.id_map == {
        "blk_22222222222222222222222222222222": result.document.blocks[0].id
    }
    assert result.document.blocks[0].id != "blk_22222222222222222222222222222222"


def test_metadata_updates_preserve_presence_and_support_annotations() -> None:
    parent = _document(
        _block(
            "blk_11111111111111111111111111111111",
            "text",
            scene_id=2,
            annotations={"emotions": ["平静"], "foo": "old", "gone": True},
        )
    )

    result = resolve_authoring(
        parent,
        None,
        {
            "blk_11111111111111111111111111111111": {
                "attrs": {"scene_id": None},
                "annotations": {"foo": "", "nullable": None},
                "remove_annotations": ["gone"],
            }
        },
    )

    block = result.document.blocks[0]
    assert block.attrs.scene_id is None
    assert block.annotations == {"emotions": ["平静"], "foo": "", "nullable": None}


def test_heading_transition_clears_level_and_non_heading_level_patch_is_invalid() -> (
    None
):
    parent = _document(
        _block(
            "blk_11111111111111111111111111111111",
            "見出し",
            block_type="heading",
            heading_level=2,
        )
    )

    narration_html = (
        '<p id="blk_11111111111111111111111111111111" data-np-type="narration">本文</p>'
    )
    result = resolve_authoring(parent, narration_html, None)
    assert result.document.blocks[0].type == "narration"
    assert result.document.blocks[0].attrs.heading_level is None

    with pytest.raises(ValidationError, match="heading_level"):
        resolve_authoring(
            parent,
            narration_html,
            {"blk_11111111111111111111111111111111": {"attrs": {"heading_level": 2}}},
        )


def test_forced_heading_same_level_is_ok_but_conflicting_metadata_is_rejected() -> None:
    parent = _document(
        _block(
            "blk_11111111111111111111111111111111",
            "見出し",
            block_type="heading",
            heading_level=2,
        )
    )
    html = '<h2 id="blk_11111111111111111111111111111111">見出し</h2>'
    same = resolve_authoring(
        parent,
        html,
        {"blk_11111111111111111111111111111111": {"attrs": {"heading_level": 2}}},
    )
    assert same.document.blocks[0].attrs.heading_level == 2

    with pytest.raises(ValidationError, match="conflict"):
        resolve_authoring(
            parent,
            html,
            {"blk_11111111111111111111111111111111": {"attrs": {"heading_level": 3}}},
        )


def test_snapshot_and_metadata_targets_reject_deleted_or_unknown_blocks() -> None:
    parent = _document(
        _block("blk_11111111111111111111111111111111", "A"),
        _block("blk_22222222222222222222222222222222", "B"),
    )

    with pytest.raises(ValidationError, match="target"):
        resolve_authoring(
            parent,
            '<p id="blk_11111111111111111111111111111111">A</p>',
            {"blk_22222222222222222222222222222222": {"annotations": {"x": 1}}},
        )
    with pytest.raises(ValidationError, match="target"):
        resolve_authoring(
            parent,
            None,
            {"unknown": {"annotations": {"x": 1}}},
        )


def test_empty_metadata_commands_and_set_remove_conflicts_are_rejected() -> None:
    parent = _document(_block("blk_11111111111111111111111111111111", "A"))

    with pytest.raises(ValidationError, match="metadata_updates"):
        resolve_authoring(parent, None, {})
    with pytest.raises(ValidationError, match="empty"):
        resolve_authoring(
            parent,
            None,
            {"blk_11111111111111111111111111111111": {}},
        )
    with pytest.raises(ValidationError, match="conflict"):
        resolve_authoring(
            parent,
            '<p id="blk_11111111111111111111111111111111" data-ann-foo="html">A</p>',
            {
                "blk_11111111111111111111111111111111": {
                    "annotations": {"foo": "metadata"}
                }
            },
        )
    with pytest.raises(ValidationError, match="remove"):
        resolve_authoring(
            parent,
            None,
            {
                "blk_11111111111111111111111111111111": {
                    "annotations": {"foo": "set"},
                    "remove_annotations": ["foo"],
                }
            },
        )


def test_authoring_returns_document_schema_errors_for_invalid_result() -> None:
    with pytest.raises(DocumentSchemaError):
        resolve_authoring(
            None,
            '<h2 id="new"> </h2>',
            None,
        )
