from __future__ import annotations

from novel_core.style_analysis.metrics import (
    BASIC_METRIC_DEFINITIONS,
    calculate_basic_metrics,
)
from novel_core.style_analysis.structure_models import (
    BlockRecord,
    SceneRecord,
    SentenceRecord,
)


def _structure() -> tuple[
    tuple[SceneRecord, ...], tuple[BlockRecord, ...], tuple[SentenceRecord, ...]
]:
    scenes = (
        SceneRecord(1, 10, 1, 0, 19),
        SceneRecord(2, 10, 2, 21, 25),
    )
    blocks = (
        BlockRecord(11, 10, 1, 1, 1, "narration", 0, 5),
        BlockRecord(12, 10, 1, 2, 1, "dialogue", 5, 15),
        BlockRecord(13, 10, 1, 3, 2, "narration", 15, 19),
        BlockRecord(14, 10, 2, 4, 3, "dialogue", 21, 25),
    )
    sentences = (
        SentenceRecord(21, 11, 1, 0, 5),
        SentenceRecord(22, 12, 1, 5, 10),
        SentenceRecord(23, 12, 2, 10, 15),
        SentenceRecord(24, 14, 1, 21, 25),
    )
    return scenes, blocks, sentences


def test_basic_metric_registry_is_explicit_and_complete() -> None:
    assert len(BASIC_METRIC_DEFINITIONS) == 15
    assert BASIC_METRIC_DEFINITIONS["text.char_count"].value_type == "int"
    assert BASIC_METRIC_DEFINITIONS["sentence.len.p50"].value_type == "float"
    assert all(
        definition.zero_width_tolerance > 0
        for definition in BASIC_METRIC_DEFINITIONS.values()
    )


def test_basic_metrics_calculate_document_and_scene_scopes() -> None:
    scenes, blocks, sentences = _structure()
    results = calculate_basic_metrics(
        document_id=99,
        canonical_text="春です。「はい。いいえ。」静か。\n\n「また。」",
        scenes=scenes,
        blocks=blocks,
        sentences=sentences,
    )
    document = {
        result.metric_name: result
        for result in results
        if result.target_type == "document"
    }
    assert document["text.char_count"].value == 23
    assert document["dialogue.utterance_count"].value == 2
    assert document["dialogue.char_ratio"].value == 14 / 23
    assert document["sentence.len.p50"].sample_count == 4
    assert document["dialogue.turn_count.p50"].value == 1.0
    scene_results = [result for result in results if result.target_type == "scene"]
    assert {result.target_id for result in scene_results} == {1, 2}


def test_basic_metrics_missing_percentiles_are_omitted_and_zero_dialogue_is_valid() -> (
    None
):
    scenes = (SceneRecord(1, 10, 1, 0, 3),)
    blocks = (BlockRecord(11, 10, 1, 1, 1, "narration", 0, 3),)
    results = calculate_basic_metrics(
        document_id=1,
        canonical_text="静か。",
        scenes=scenes,
        blocks=blocks,
        sentences=(SentenceRecord(21, 11, 1, 0, 3),),
    )
    names = {result.metric_name for result in results}
    assert "dialogue.utterance_count" in names
    assert "dialogue.char_ratio" in names
    assert "dialogue.utterance_len.p50" not in names
    assert (
        next(
            result
            for result in results
            if result.metric_name == "dialogue.utterance_count"
        ).value
        == 0
    )
    assert (
        next(
            result for result in results if result.metric_name == "dialogue.char_ratio"
        ).value
        == 0.0
    )
