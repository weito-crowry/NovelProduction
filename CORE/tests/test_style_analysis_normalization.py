from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path

import pytest
from test_style_analysis_sources import open_test_database

from novel_core.errors import ValidationError
from novel_core.style_analysis.normalization import normalize_text
from novel_core.style_analysis.source_models import SourceEpisodeInput, SourceWorkInput
from novel_core.style_analysis.source_repository import StyleSourceRepository
from novel_core.style_analysis.text_service import StyleTextService


def _formal_source(connection: sqlite3.Connection) -> tuple[int, int]:
    repository = StyleSourceRepository(connection)
    result = repository.insert_import(
        source_type="text",
        external_work_id=hashlib.sha256(b"source").hexdigest(),
        original_filename="book.txt",
        adapter_id="style-source-text",
        adapter_version=1,
        payload=b"source",
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
                    raw_text="provisional",
                    metadata={"scene_break_offsets_raw": []},
                ),
            ),
        ),
    )
    connection.commit()
    episode = repository.list_reference_episodes(result.work.id)[0]
    assert episode.style_document_id is not None
    return episode.style_document_id, episode.latest_snapshot_id


def test_formal_normalization_preserves_raw_and_maps_hints(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path)
    try:
        document_id, snapshot_id = _formal_source(connection)
        revision = StyleTextService(connection).insert_normalized_reference_revision(
            document_id=document_id,
            source_snapshot_id=snapshot_id,
            raw_text="\ufeff第一行  \r\n\r\n\r\n第二\t行\r\n",
            structure_hints_raw=[12],
        )
        assert revision.normalizer_id == "canonical-japanese-fiction"
        assert revision.normalizer_version == 1
        assert revision.raw_text.startswith("\ufeff")
        assert revision.canonical_text == "第一行\n\n第二 行"
        metadata = json.loads(revision.metadata_json)
        assert metadata["structure_hints"]["scene_break_offsets_cp"] == [5]
        mappings = connection.execute(
            "SELECT raw_start, raw_end, canonical_start, canonical_end, operation "
            "FROM style_text_mappings WHERE text_revision_id = ? "
            "ORDER BY segment_order",
            (revision.id,),
        ).fetchall()
        assert mappings
        assert all(row[1] >= row[0] and row[3] >= row[2] for row in mappings)
        assert any(row[4] == "collapse" for row in mappings)
    finally:
        connection.close()


def test_formal_normalization_reuses_only_same_input_and_leaves_provisional(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path)
    try:
        document_id, snapshot_id = _formal_source(connection)
        service = StyleTextService(connection)
        provisional = service.insert_reference_revision(
            document_id=document_id,
            source_snapshot_id=snapshot_id,
            raw_text="same",
            structure_hints_raw=[],
        )
        formal = service.insert_normalized_reference_revision(
            document_id=document_id,
            source_snapshot_id=snapshot_id,
            raw_text="same",
            structure_hints_raw=[],
        )
        reused = service.insert_normalized_reference_revision(
            document_id=document_id,
            source_snapshot_id=snapshot_id,
            raw_text="same",
            structure_hints_raw=[],
        )
        assert provisional.normalizer_id == "sa-b-provisional-raw-bridge"
        assert formal.normalizer_id == "canonical-japanese-fiction"
        assert reused.id == formal.id
        assert connection.execute(
            "SELECT COUNT(*) FROM style_text_mappings WHERE text_revision_id = ?",
            (formal.id,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT normalizer_id FROM style_text_revisions WHERE id = ?",
            (provisional.id,),
        ).fetchone() == ("sa-b-provisional-raw-bridge",)
    finally:
        connection.close()


def test_formal_normalization_rejects_invalid_hint(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path)
    try:
        document_id, snapshot_id = _formal_source(connection)
        with pytest.raises(ValidationError, match="STRUCTURE_HINTS_INVALID"):
            StyleTextService(connection).insert_normalized_reference_revision(
                document_id=document_id,
                source_snapshot_id=snapshot_id,
                raw_text="text",
                structure_hints_raw=[True],
            )
    finally:
        connection.close()


def test_normalization_rules_are_nfc_only_and_preserve_full_width_space() -> None:
    result = normalize_text(
        "\ufeff  e\u0301①\t　\x00\x0b\r\n\r\n\r\n末尾  \r\n",
        [],
    )
    assert result.canonical_text == "  é① \u3000\n\n末尾"
    assert "①" in result.canonical_text
    assert "\u3000" in result.canonical_text
    assert not result.canonical_text.endswith("\n")
    assert "\x00" not in result.canonical_text
    assert "\x0b" not in result.canonical_text


def test_nfc_alignment_handles_repeated_precomposed_character() -> None:
    result = normalize_text("e\u0301é", [])
    assert result.canonical_text == "éé"
    assert result.segments
    assert unicodedata.is_normalized("NFC", result.canonical_text)


def test_nfc_alignment_maps_combining_sequence_and_raw_boundary() -> None:
    assert normalize_text("a\u0301a", []).canonical_text == "áa"
    result = normalize_text("e\u0301é", [2])
    assert result.scene_break_offsets_cp == (1,)


def test_nfc_alignment_handles_hangul_jamo_composition() -> None:
    result = normalize_text("\u1100\u1161", [])
    assert result.canonical_text == "가"
    assert unicodedata.is_normalized("NFC", result.canonical_text)
    assert normalize_text("가\u11a8", []).canonical_text == "각"


def test_nfc_alignment_handles_non_hangul_canonical_composition() -> None:
    result = normalize_text("\u09c7\u09be", [])
    assert ord(result.canonical_text) == 0x09CB
    assert unicodedata.is_normalized("NFC", result.canonical_text)


def test_nfc_alignment_handles_decomposing_mark_reordering() -> None:
    raw_text = "A\u0305\u0f73"
    result = normalize_text(raw_text, [])
    assert result.canonical_text == unicodedata.normalize("NFC", raw_text)
    assert unicodedata.is_normalized("NFC", result.canonical_text)


def test_nfc_alignment_looks_through_decomposing_starters() -> None:
    raw_text = "A\u0619\u0f81\ua9c0"
    result = normalize_text(raw_text, [])
    assert result.canonical_text == unicodedata.normalize("NFC", raw_text)
    assert unicodedata.is_normalized("NFC", result.canonical_text)


def test_controls_and_tabs_are_processed_inside_reordered_pieces() -> None:
    assert normalize_text("\x00\u0315\u0300A", []).canonical_text == "\u0300\u0315A"
    assert normalize_text("\t\u0315\u0300A", []).canonical_text == " \u0300\u0315A"


def test_normalization_collapses_and_trims_blank_lines_after_space_removal() -> None:
    assert normalize_text("A\n \n \nB", []).canonical_text == "A\n\nB"
    assert normalize_text("\n\n\n本文", []).canonical_text == "本文"
    with pytest.raises(ValidationError, match="TEXT_EMPTY"):
        normalize_text("\n \n \n", [])


def test_control_removal_does_not_make_internal_space_trailing() -> None:
    assert normalize_text("A \x00B", []).canonical_text == "A B"


def test_adjacent_replacements_keep_unique_raw_hint_boundary() -> None:
    result = normalize_text("e\u0301a\u0301", [2])
    assert result.canonical_text == "éá"
    assert result.scene_break_offsets_cp == (1,)


def test_normalization_empty_and_code_point_limit_errors() -> None:
    with pytest.raises(ValidationError, match="TEXT_EMPTY"):
        normalize_text("\x00\n\n", [])
    with pytest.raises(ValidationError, match="TEXT_TOO_LARGE"):
        normalize_text("a" * 2_000_001, [])
    assert normalize_text("a" * 2_000_000, []).canonical_text == "a" * 2_000_000
