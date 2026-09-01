from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from novel_core.style_analysis.metrics import MetricMeasurement, percentile
from novel_core.style_analysis.semantic_metric_support import (
    annotation_records,
    effective_block_label,
    effective_novelty,
    effective_speaker,
    eligible_persons,
    is_question,
    load_annotations,
    speaker_streaks,
    utterance_length,
)
from novel_core.style_analysis.structure_models import BlockRecord, SceneRecord
from novel_core.style_analysis.term_repository import TermRepository

TargetType = Literal["document", "scene", "character"]


@dataclass(frozen=True, slots=True)
class SemanticMetricResult:
    measurements: tuple[MetricMeasurement, ...]
    partial: bool


def calculate_semantic_metrics(
    connection: sqlite3.Connection,
    *,
    document_id: int,
    canonical_text: str,
    scenes: Sequence[SceneRecord],
    blocks: Sequence[BlockRecord],
    speaker_run_id: int | None,
    term_run_id: int | None,
    explanation_run_id: int | None,
    block_run_id: int | None,
    speaker_threshold: float = 0.85,
    block_threshold: float = 0.75,
    term_explanation_threshold: float = 0.85,
    term_first_appearance_complete: bool = True,
) -> SemanticMetricResult:
    partial = any(
        run_id is None
        for run_id in (speaker_run_id, term_run_id, explanation_run_id, block_run_id)
    )
    result = _composition_metrics(
        connection,
        canonical_text,
        document_id,
        scenes,
        blocks,
        block_run_id,
        block_threshold,
    )
    speaker, speaker_partial = _speaker_metrics(
        connection, canonical_text, blocks, speaker_run_id, speaker_threshold
    )
    result.extend(speaker)
    terms, term_partial = _term_metrics(
        connection,
        canonical_text,
        document_id,
        scenes,
        blocks,
        term_run_id,
        explanation_run_id,
        term_first_appearance_complete,
        term_explanation_threshold,
    )
    result.extend(terms)
    return SemanticMetricResult(
        tuple(result), partial or speaker_partial or term_partial
    )


def _composition_metrics(
    connection: sqlite3.Connection,
    text: str,
    document_id: int,
    scenes: Sequence[SceneRecord],
    blocks: Sequence[BlockRecord],
    run_id: int | None,
    threshold: float,
) -> list[MetricMeasurement]:
    if run_id is None:
        return []
    annotation_map = load_annotations(connection, run_id, "block.semantic_primary")
    result: list[MetricMeasurement] = []
    for target_type, target_id, scope in _scopes(document_id, scenes, blocks):
        usable = tuple(
            block for block in scope if block.block_type in {"dialogue", "narration"}
        )
        denominator = sum(
            _chars(text[block.start_cp : block.end_cp]) for block in usable
        )
        if denominator == 0:
            continue
        narration = tuple(block for block in usable if block.block_type == "narration")
        labels: dict[int, str] = {}
        for block in narration:
            label, source = effective_block_label(
                connection, block.id, run_id, annotation_map.get(block.id), threshold
            )
            if label is None or source == "unknown":
                break
            labels[block.id] = label
        else:
            for label in (
                "action",
                "description",
                "exposition",
                "psychology",
                "transition",
            ):
                numerator = sum(
                    _chars(text[block.start_cp : block.end_cp])
                    for block in narration
                    if labels.get(block.id) == label
                )
                result.append(
                    MetricMeasurement(
                        target_type,
                        target_id,
                        f"semantic.{label}.char_ratio",
                        1,
                        numerator / denominator,
                        len(usable),
                    )
                )
    return result


def _speaker_metrics(
    connection: sqlite3.Connection,
    text: str,
    blocks: Sequence[BlockRecord],
    run_id: int | None,
    threshold: float,
) -> tuple[list[MetricMeasurement], bool]:
    if run_id is None:
        return [], True
    annotation_map = load_annotations(connection, run_id, "speaker")
    by_entity: dict[int, list[BlockRecord]] = {
        entity_id: [] for entity_id in eligible_persons(connection, run_id)
    }
    speaker_by_block: dict[int, int | None] = {}
    for block in sorted(blocks, key=lambda item: (item.order_index, item.id)):
        if block.block_type != "dialogue":
            continue
        entity_id = effective_speaker(
            connection, block.id, run_id, annotation_map.get(block.id), threshold
        )
        speaker_by_block[block.id] = entity_id
        if entity_id is not None and entity_id in by_entity:
            by_entity[entity_id].append(block)
    streaks = speaker_streaks(text, blocks, speaker_by_block)
    result: list[MetricMeasurement] = []
    for entity_id, utterances in sorted(by_entity.items()):
        result.append(
            MetricMeasurement(
                "character", entity_id, "speaker.utterance_count", 1, len(utterances), 1
            )
        )
        if not utterances:
            continue
        lengths = [
            utterance_length(text[item.start_cp : item.end_cp]) for item in utterances
        ]
        questions = sum(
            is_question(text[item.start_cp : item.end_cp]) for item in utterances
        )
        result.extend(
            (
                MetricMeasurement(
                    "character",
                    entity_id,
                    "speaker.utterance_len.p50",
                    1,
                    percentile([float(item) for item in lengths], 0.50),
                    len(lengths),
                ),
                MetricMeasurement(
                    "character",
                    entity_id,
                    "speaker.utterance_len.p90",
                    1,
                    percentile([float(item) for item in lengths], 0.90),
                    len(lengths),
                ),
                MetricMeasurement(
                    "character",
                    entity_id,
                    "speaker.question_ratio",
                    1,
                    questions / len(utterances),
                    len(utterances),
                ),
                MetricMeasurement(
                    "character",
                    entity_id,
                    "speaker.consecutive_turns.p50",
                    1,
                    percentile(
                        [float(item) for item in streaks.get(entity_id, [1])], 0.50
                    ),
                    len(utterances),
                ),
            )
        )
    return result, False


def _term_metrics(
    connection: sqlite3.Connection,
    text: str,
    document_id: int,
    scenes: Sequence[SceneRecord],
    blocks: Sequence[BlockRecord],
    term_run_id: int | None,
    explanation_run_id: int | None,
    first_appearance_complete: bool,
    explanation_threshold: float,
) -> tuple[list[MetricMeasurement], bool]:
    if term_run_id is None or not first_appearance_complete:
        return [], True
    mentions = TermRepository(connection).list_mentions(analysis_run_id=term_run_id)
    novelty: dict[int, object] = {}
    for subject_id, value_json, confidence, start_cp in annotation_records(
        connection, term_run_id, "term.novelty"
    ):
        novelty[subject_id] = effective_novelty(
            connection,
            subject_id,
            term_run_id,
            (subject_id, value_json, confidence, start_cp),
        )
    eligible = {
        term_id
        for term_id, value in novelty.items()
        if value in {"work_specific", "specialized_real_world"}
    }
    order = {block.id: (block.order_index, block.start_cp) for block in blocks}
    first_by_term: dict[int, tuple[tuple[int, int, int], Any]] = {}
    for mention in mentions:
        if mention.term_id not in eligible:
            continue
        key = (*order.get(mention.block_id, (0, mention.start_cp)), mention.id)
        if (
            mention.term_id not in first_by_term
            or key < first_by_term[mention.term_id][0]
        ):
            first_by_term[mention.term_id] = (key, mention)
    explanations: dict[int, tuple[int, int]] = {}
    for subject_id, value_json, confidence, start_cp in annotation_records(
        connection, explanation_run_id, "term_explanation"
    ):
        if (
            _field(value_json, "completeness") != "sufficient"
            or not isinstance(confidence, (int, float))
            or confidence < explanation_threshold
            or not isinstance(start_cp, int)
        ):
            continue
        block_id = _field(value_json, "block_id")
        if isinstance(block_id, int) and not isinstance(block_id, bool):
            explanations[subject_id] = block_id, start_cp
    scene_by_block = {block.id: block.scene_id for block in blocks}
    result: list[MetricMeasurement] = []
    for target_type, target_id, scope in _scopes(document_id, scenes, blocks):
        scope_ids = {block.id for block in scope}
        selected = [
            mention
            for _, mention in first_by_term.values()
            if mention.block_id in scope_ids
        ]
        chars = sum(
            _chars(text[block.start_cp : block.end_cp])
            for block in scope
            if block.block_type in {"dialogue", "narration"}
        )
        if chars == 0:
            continue
        result.append(
            MetricMeasurement(
                target_type,
                target_id,
                "term.new_per_1000_chars",
                1,
                len(selected) * 1000 / chars,
                len(selected),
            )
        )
        explained = [
            mention
            for mention in selected
            if mention.id in explanations
            and scene_by_block.get(explanations[mention.id][0]) == mention.scene_id
        ]
        result.append(
            MetricMeasurement(
                target_type,
                target_id,
                "term.explained_same_scene_ratio",
                1,
                len(explained) / len(selected) if selected else 0.0,
                len(selected),
            )
        )
        delays = [
            float(explanations[mention.id][1] - mention.start_cp)
            for mention in explained
        ]
        if delays:
            result.extend(
                (
                    MetricMeasurement(
                        target_type,
                        target_id,
                        "term.explanation_delay.p50",
                        1,
                        percentile(delays, 0.50),
                        len(delays),
                    ),
                    MetricMeasurement(
                        target_type,
                        target_id,
                        "term.explanation_delay.p90",
                        1,
                        percentile(delays, 0.90),
                        len(delays),
                    ),
                )
            )
    return result, False


def _scopes(
    document_id: int, scenes: Sequence[SceneRecord], blocks: Sequence[BlockRecord]
) -> Iterable[tuple[TargetType, int, tuple[BlockRecord, ...]]]:
    yield "document", document_id, tuple(blocks)
    for scene in scenes:
        yield (
            "scene",
            scene.id,
            tuple(block for block in blocks if block.scene_id == scene.id),
        )


def _field(value_json: object, key: str) -> object:
    import json

    try:
        value = json.loads(str(value_json))
    except (TypeError, json.JSONDecodeError):
        return None
    return value.get(key) if isinstance(value, dict) else None


def _chars(value: str) -> int:
    return sum(not character.isspace() for character in value)
