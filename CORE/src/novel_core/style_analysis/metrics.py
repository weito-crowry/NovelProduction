from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Literal

from novel_core.style_analysis.structure_models import (
    BlockRecord,
    SceneRecord,
    SentenceRecord,
)


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    name: str
    version: int
    unit: str
    value_type: Literal["int", "float"]
    scope_types: tuple[Literal["document", "scene", "character"], ...]
    group: Literal["basic", "semantic"]
    description: str
    zero_width_tolerance: float


@dataclass(frozen=True, slots=True)
class MetricMeasurement:
    target_type: Literal["document", "scene", "character"]
    target_id: int
    metric_name: str
    metric_version: int
    value: int | float
    sample_count: int


def _basic(
    name: str, unit: str, value_type: Literal["int", "float"], tolerance: float
) -> MetricDefinition:
    return MetricDefinition(
        name=name,
        version=1,
        unit=unit,
        value_type=value_type,
        scope_types=("document", "scene"),
        group="basic",
        description=name,
        zero_width_tolerance=tolerance,
    )


BASIC_METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "text.char_count": _basic("text.char_count", "chars", "int", 5.0),
    "sentence.len.p50": _basic("sentence.len.p50", "chars", "float", 5.0),
    "sentence.len.p90": _basic("sentence.len.p90", "chars", "float", 5.0),
    "block.len.p50": _basic("block.len.p50", "chars", "float", 5.0),
    "block.len.p90": _basic("block.len.p90", "chars", "float", 5.0),
    "paragraph.len.p50": _basic("paragraph.len.p50", "chars", "float", 5.0),
    "paragraph.len.p90": _basic("paragraph.len.p90", "chars", "float", 5.0),
    "dialogue.char_ratio": _basic("dialogue.char_ratio", "ratio", "float", 0.02),
    "dialogue.utterance_count": _basic("dialogue.utterance_count", "count", "int", 1.0),
    "dialogue.utterance_len.p50": _basic(
        "dialogue.utterance_len.p50", "chars", "float", 5.0
    ),
    "dialogue.utterance_len.p90": _basic(
        "dialogue.utterance_len.p90", "chars", "float", 5.0
    ),
    "dialogue.turn_count.p50": _basic("dialogue.turn_count.p50", "count", "float", 1.0),
    "dialogue.turn_count.p90": _basic("dialogue.turn_count.p90", "count", "float", 1.0),
    "narration.run_len.p50": _basic("narration.run_len.p50", "chars", "float", 5.0),
    "narration.run_len.p90": _basic("narration.run_len.p90", "chars", "float", 5.0),
}


def calculate_basic_metrics(
    *,
    document_id: int,
    canonical_text: str,
    scenes: tuple[SceneRecord, ...],
    blocks: tuple[BlockRecord, ...],
    sentences: tuple[SentenceRecord, ...],
) -> tuple[MetricMeasurement, ...]:
    usable_blocks = tuple(
        block for block in blocks if block.block_type in {"dialogue", "narration"}
    )
    by_scene = {
        scene.id: tuple(block for block in usable_blocks if block.scene_id == scene.id)
        for scene in scenes
    }
    result: list[MetricMeasurement] = []
    result.extend(
        _scope_metrics(
            "document",
            document_id,
            canonical_text,
            usable_blocks,
            sentences,
            blocks,
        )
    )
    all_by_scene = {
        scene.id: tuple(block for block in blocks if block.scene_id == scene.id)
        for scene in scenes
    }
    for scene in scenes:
        result.extend(
            _scope_metrics(
                "scene",
                scene.id,
                canonical_text,
                by_scene[scene.id],
                tuple(
                    sentence
                    for sentence in sentences
                    if any(
                        block.id == sentence.block_id for block in by_scene[scene.id]
                    )
                ),
                all_by_scene[scene.id],
            )
        )
    return tuple(result)


def _scope_metrics(
    target_type: Literal["document", "scene"],
    target_id: int,
    text: str,
    blocks: tuple[BlockRecord, ...],
    sentences: tuple[SentenceRecord, ...],
    ordered_blocks: tuple[BlockRecord, ...],
) -> list[MetricMeasurement]:
    result: list[MetricMeasurement] = []
    block_lengths = [
        _metric_char_count(text[block.start_cp : block.end_cp]) for block in blocks
    ]
    sentence_lengths = [
        _metric_char_count(text[sentence.start_cp : sentence.end_cp])
        for sentence in sentences
    ]
    paragraph_lengths: dict[int, int] = {}
    for block in blocks:
        paragraph_lengths[block.paragraph_index] = paragraph_lengths.get(
            block.paragraph_index, 0
        ) + _metric_char_count(text[block.start_cp : block.end_cp])
    result.append(
        _measurement(target_type, target_id, "text.char_count", sum(block_lengths), 1)
    )
    result.extend(
        _percentiles(target_type, target_id, "sentence.len", sentence_lengths)
    )
    result.extend(_percentiles(target_type, target_id, "block.len", block_lengths))
    result.extend(
        _percentiles(
            target_type, target_id, "paragraph.len", list(paragraph_lengths.values())
        )
    )
    dialogue = tuple(block for block in blocks if block.block_type == "dialogue")
    dialogue_chars = sum(
        _metric_char_count(text[block.start_cp : block.end_cp]) for block in dialogue
    )
    total_chars = sum(block_lengths)
    if total_chars:
        result.append(
            _measurement(
                target_type,
                target_id,
                "dialogue.char_ratio",
                dialogue_chars / total_chars,
                len(blocks),
            )
        )
    result.append(
        _measurement(
            target_type, target_id, "dialogue.utterance_count", len(dialogue), 1
        )
    )
    utterance_lengths = [
        _outer_quote_length(text[block.start_cp : block.end_cp]) for block in dialogue
    ]
    result.extend(
        _percentiles(
            target_type, target_id, "dialogue.utterance_len", utterance_lengths
        )
    )
    turn_counts = _turn_counts(ordered_blocks, text)
    result.extend(
        _percentiles(target_type, target_id, "dialogue.turn_count", turn_counts)
    )
    narration_runs = _narration_runs(ordered_blocks, text)
    result.extend(
        _percentiles(target_type, target_id, "narration.run_len", narration_runs)
    )
    return result


def _measurement(
    target_type: Literal["document", "scene"],
    target_id: int,
    name: str,
    value: int | float,
    sample_count: int,
) -> MetricMeasurement:
    definition = BASIC_METRIC_DEFINITIONS[name]
    return MetricMeasurement(
        target_type, target_id, name, definition.version, value, sample_count
    )


def _percentiles(
    target_type: Literal["document", "scene"],
    target_id: int,
    prefix: str,
    values: list[int],
) -> list[MetricMeasurement]:
    if not values:
        return []
    return [
        _measurement(
            target_type,
            target_id,
            f"{prefix}.p50",
            _percentile(values, 0.50),
            len(values),
        ),
        _measurement(
            target_type,
            target_id,
            f"{prefix}.p90",
            _percentile(values, 0.90),
            len(values),
        ),
    ]


def _percentile(values: list[int], quantile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = floor(index)
    upper = min(lower + 1, len(ordered) - 1)
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower))


def percentile(values: list[float], quantile: float) -> float:
    """Return the v1 linear-interpolation percentile used by all metrics."""
    if not values:
        raise ValueError("PERCENTILE_EMPTY")
    ordered = sorted(float(value) for value in values)
    index = (len(ordered) - 1) * quantile
    lower = floor(index)
    upper = min(lower + 1, len(ordered) - 1)
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower))


def _outer_quote_length(value: str) -> int:
    if value.startswith("「") and value.endswith("」") and len(value) >= 2:
        return _metric_char_count(value[1:-1])
    return _metric_char_count(value)


def _metric_char_count(value: str) -> int:
    return sum(not character.isspace() for character in value)


def _turn_counts(blocks: tuple[BlockRecord, ...], text: str) -> list[int]:
    counts: list[int] = []
    current = 0
    current_scene: int | None = None
    for index, block in enumerate(blocks):
        if current and block.scene_id != current_scene:
            counts.append(current)
            current = 0
        if block.block_type == "dialogue" and current_scene != block.scene_id:
            current_scene = block.scene_id
        if block.block_type == "dialogue":
            current += 1
            continue
        bridged = (
            block.block_type == "narration"
            and current > 0
            and _metric_char_count(text[block.start_cp : block.end_cp]) <= 40
            and index + 1 < len(blocks)
            and blocks[index + 1].block_type == "dialogue"
            and blocks[index + 1].scene_id == block.scene_id
        )
        if not bridged:
            if current:
                counts.append(current)
            current = 0
    if current:
        counts.append(current)
    return counts


def _narration_runs(blocks: tuple[BlockRecord, ...], text: str) -> list[int]:
    result: list[int] = []
    current_scene: int | None = None
    current = 0
    for block in blocks:
        if block.block_type == "narration" and block.scene_id == current_scene:
            current += _metric_char_count(text[block.start_cp : block.end_cp])
        else:
            if current:
                result.append(current)
            current_scene = block.scene_id
            current = (
                _metric_char_count(text[block.start_cp : block.end_cp])
                if block.block_type == "narration"
                else 0
            )
    if current:
        result.append(current)
    return result
