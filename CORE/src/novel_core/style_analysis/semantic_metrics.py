from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from novel_core.style_analysis.metrics import MetricMeasurement, percentile
from novel_core.style_analysis.semantic_metric_support import (
    annotation_records,
    eligible_persons,
    is_question,
    load_annotations,
    resolve_block_semantic,
    resolve_speaker,
    resolve_term_mention_explanation,
    resolve_term_novelty,
    speaker_streaks,
    utterance_length,
)
from novel_core.style_analysis.structure_models import BlockRecord, SceneRecord
from novel_core.style_analysis.term_models import TermMentionRecord
from novel_core.style_analysis.term_prefix import TermPrefixEntry
from novel_core.style_analysis.term_repository import TermRepository

TargetType = Literal["document", "scene", "character"]


@dataclass(frozen=True, slots=True)
class SemanticMetricResult:
    measurements: tuple[MetricMeasurement, ...]
    partial: bool
    failed: bool = False


@dataclass(frozen=True, slots=True)
class _BranchResult:
    measurements: tuple[MetricMeasurement, ...]
    incomplete: bool = False
    unavailable: bool = False


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
    term_prefix_entries: Sequence[TermPrefixEntry] = (),
) -> SemanticMetricResult:
    branches = (
        _composition_metrics(
            connection,
            canonical_text,
            document_id,
            scenes,
            blocks,
            block_run_id,
            block_threshold,
        ),
        _speaker_metrics(
            connection, canonical_text, blocks, speaker_run_id, speaker_threshold
        ),
        _term_metrics(
            connection,
            canonical_text,
            document_id,
            scenes,
            blocks,
            term_run_id,
            explanation_run_id,
            term_first_appearance_complete,
            term_explanation_threshold,
            term_prefix_entries,
        ),
    )
    measurements = tuple(
        measurement for branch in branches for measurement in branch.measurements
    )
    incomplete = any(branch.incomplete for branch in branches)
    unavailable = any(branch.unavailable for branch in branches)
    return SemanticMetricResult(
        measurements,
        partial=incomplete or unavailable,
        failed=not measurements and (incomplete or unavailable),
    )


def _composition_metrics(
    connection: sqlite3.Connection,
    text: str,
    document_id: int,
    scenes: Sequence[SceneRecord],
    blocks: Sequence[BlockRecord],
    run_id: int | None,
    threshold: float,
) -> _BranchResult:
    if run_id is None:
        return _BranchResult((), unavailable=True)
    status = _run_status(connection, run_id)
    if status in {"failed", "running", "cancelled"}:
        return _BranchResult((), unavailable=True)
    annotation_map = load_annotations(connection, run_id, "block.semantic_primary")
    result: list[MetricMeasurement] = []
    incomplete = False
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
        if not narration:
            continue
        labels: dict[int, str] = {}
        for block in narration:
            effective = resolve_block_semantic(
                connection, block.id, run_id, annotation_map.get(block.id), threshold
            )
            if not isinstance(effective.value, str):
                incomplete = True
                break
            labels[block.id] = effective.value
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
    return _BranchResult(tuple(result), incomplete=incomplete or status == "partial")


def _speaker_metrics(
    connection: sqlite3.Connection,
    text: str,
    blocks: Sequence[BlockRecord],
    run_id: int | None,
    threshold: float,
) -> _BranchResult:
    if run_id is None:
        return _BranchResult((), unavailable=True)
    status = _run_status(connection, run_id)
    if status in {"failed", "running", "cancelled"}:
        return _BranchResult((), unavailable=True)
    annotation_map = load_annotations(connection, run_id, "speaker")
    entity_run_id = _entity_resolver_run_id(connection, run_id)
    by_entity: dict[int, list[BlockRecord]] = {
        entity_id: []
        for entity_id in eligible_persons(
            connection,
            run_id,
            blocks=blocks,
            entity_run_id=entity_run_id,
            threshold=threshold,
        )
    }
    speaker_by_block: dict[int, int | None] = {}
    incomplete = False
    for block in sorted(blocks, key=lambda item: (item.order_index, item.id)):
        if block.block_type != "dialogue":
            continue
        effective = resolve_speaker(
            connection, block.id, run_id, annotation_map.get(block.id), threshold
        )
        entity_id = effective.value if isinstance(effective.value, int) else None
        speaker_by_block[block.id] = entity_id
        if entity_id is not None and entity_id in by_entity:
            by_entity[entity_id].append(block)
    if not by_entity:
        return _BranchResult((), incomplete=incomplete)
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
            )
        )
        streak_values = streaks.get(entity_id, [])
        if streak_values:
            result.append(
                MetricMeasurement(
                    "character",
                    entity_id,
                    "speaker.consecutive_turns.p50",
                    1,
                    percentile([float(item) for item in streak_values], 0.50),
                    len(streak_values),
                )
            )
    return _BranchResult(tuple(result), incomplete=incomplete or status == "partial")


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
    prefix_entries: Sequence[TermPrefixEntry],
) -> _BranchResult:
    if term_run_id is None:
        return _BranchResult((), unavailable=True)
    term_status = _run_status(connection, term_run_id)
    if term_status in {"failed", "running", "cancelled"}:
        return _BranchResult((), unavailable=True)
    if not first_appearance_complete:
        return _BranchResult((), incomplete=True)
    entries = tuple(prefix_entries) or (
        TermPrefixEntry(0, 0, document_id, 0, 0, term_run_id),
    )
    repository = TermRepository(connection)
    first_by_term: dict[int, tuple[tuple[int, int, int], TermMentionRecord]] = {}
    current_mentions: dict[int, TermMentionRecord] = {}
    for entry in entries:
        novelty: dict[int, object] = {}
        for subject_id, value_json, confidence, start_cp in annotation_records(
            connection, entry.term_run_id, "term.novelty"
        ):
            novelty[subject_id] = resolve_term_novelty(
                connection,
                subject_id,
                entry.term_run_id,
                (subject_id, value_json, confidence, start_cp),
            ).value
        mentions = repository.list_mentions(analysis_run_id=entry.term_run_id)
        for mention in mentions:
            if entry.document_id == document_id:
                current_mentions[mention.id] = mention
            if novelty.get(mention.term_id) not in {
                "work_specific",
                "specialized_real_world",
            }:
                continue
            key = (entry.episode_order, mention.start_cp, mention.id)
            previous = first_by_term.get(mention.term_id)
            if previous is None or key < previous[0]:
                first_by_term[mention.term_id] = (key, mention)
    current_first = tuple(
        mention
        for _, mention in first_by_term.values()
        if mention.id in current_mentions
    )
    scene_by_block = {block.id: block.scene_id for block in blocks}
    result: list[MetricMeasurement] = []
    incomplete = term_status == "partial"
    explanation_status = (
        _run_status(connection, explanation_run_id)
        if explanation_run_id is not None
        else None
    )
    explanation_unavailable = explanation_status in {"failed", "running", "cancelled"}
    if explanation_status == "partial":
        incomplete = True
    has_scope = False
    for target_type, target_id, scope in _scopes(document_id, scenes, blocks):
        scope_ids = {block.id for block in scope}
        selected = [
            mention for mention in current_first if mention.block_id in scope_ids
        ]
        chars = sum(
            _chars(text[block.start_cp : block.end_cp])
            for block in scope
            if block.block_type in {"dialogue", "narration"}
        )
        if chars == 0:
            continue
        has_scope = True
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
        if not selected:
            continue
        if explanation_run_id is None or explanation_unavailable:
            continue
        explained: list[tuple[TermMentionRecord, dict[str, object]]] = []
        for mention in selected:
            effective = resolve_term_mention_explanation(
                connection, mention.id, explanation_run_id, explanation_threshold
            )
            value = effective.value
            if not isinstance(value, dict):
                continue
            block_id = value.get("block_id")
            if (
                isinstance(block_id, int)
                and scene_by_block.get(block_id) == mention.scene_id
            ):
                explained.append((mention, value))
        result.append(
            MetricMeasurement(
                target_type,
                target_id,
                "term.explained_same_scene_ratio",
                1,
                len(explained) / len(selected),
                len(selected),
            )
        )
        delays = [
            float(_explanation_start(value, mention.start_cp) - mention.start_cp)
            for mention, value in explained
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
    return _BranchResult(
        tuple(result),
        incomplete=incomplete and has_scope,
        unavailable=explanation_unavailable and has_scope,
    )


def _entity_resolver_run_id(
    connection: sqlite3.Connection, speaker_run_id: int
) -> int | None:
    row = connection.execute(
        "SELECT dependency_run_id FROM style_analysis_run_dependencies links "
        "JOIN style_analysis_runs dep ON dep.id = links.dependency_run_id "
        "WHERE links.run_id = ? AND dep.analyzer_id = 'entity-resolver' "
        "ORDER BY links.dependency_run_id DESC LIMIT 1",
        (speaker_run_id,),
    ).fetchone()
    return int(row[0]) if row is not None else None


def _run_status(connection: sqlite3.Connection, run_id: int) -> str | None:
    row = connection.execute(
        "SELECT status FROM style_analysis_runs WHERE id = ?", (run_id,)
    ).fetchone()
    return None if row is None else str(row[0])


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


def _chars(value: str) -> int:
    return sum(not character.isspace() for character in value)


def _explanation_start(value: dict[str, object], fallback: int) -> int:
    start_cp = value.get("start_cp")
    return start_cp if isinstance(start_cp, int) else fallback
