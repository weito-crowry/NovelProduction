from __future__ import annotations

import json
import sqlite3

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.runtime_models import AnalysisPolicy
from novel_core.style_analysis.semantic_metric_support import (
    annotation_records,
    load_annotations,
    resolve_block_semantic,
    resolve_term_mention_explanation,
    resolve_term_novelty,
)
from novel_core.style_analysis.structure_models import BlockRecord
from novel_core.style_analysis.term_models import TermMentionRecord
from novel_core.style_analysis.term_repository import TermRepository


def build_lint_evidence(
    connection: sqlite3.Connection,
    *,
    document_id: int,
    metric_name: str,
    target_type: str,
    target_id: int,
    text_revision_id: int,
    structure_revision_id: int,
    metric_run_id: int | None,
) -> dict[str, object]:
    base: dict[str, object] = {
        "text_revision_id": text_revision_id,
        "structure_revision_id": structure_revision_id,
        "target_type": target_type,
        "target_id": target_id,
    }
    spans: list[dict[str, object]] = []
    kind = "scope_metric"
    if metric_name.startswith("narration.run_len."):
        spans = _narration_runs(
            connection, structure_revision_id, target_type, target_id
        )
        kind = "narration_run"
    elif metric_run_id is not None and metric_name == "semantic.exposition.char_ratio":
        spans = _effective_exposition_blocks(
            connection,
            structure_revision_id,
            target_type,
            target_id,
            metric_run_id,
        )
        kind = "exposition_block"
    elif metric_run_id is not None and metric_name == "term.new_per_1000_chars":
        spans = _first_appearance_mentions(
            connection,
            document_id,
            text_revision_id,
            structure_revision_id,
            target_type,
            target_id,
            metric_run_id,
        )
        kind = "term_first_appearance"
    elif metric_run_id is not None and metric_name.startswith(
        "term.explanation_delay."
    ):
        spans = _effective_explanation_spans(
            connection,
            document_id,
            text_revision_id,
            structure_revision_id,
            target_type,
            target_id,
            metric_run_id,
        )
        kind = "term_explanation_delay"
    if not spans:
        kind = "scope_metric"
    return {**base, "evidence_kind": kind, "spans": spans[:5]}


def _narration_runs(
    connection: sqlite3.Connection, structure_id: int, target_type: str, target_id: int
) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT id, scene_id, order_index, start_cp, end_cp FROM style_blocks "
        "WHERE structure_revision_id = ? AND block_type = 'narration' "
        "AND (? = 'document' OR scene_id = ?) ORDER BY order_index, id",
        (structure_id, target_type, target_id),
    ).fetchall()
    result: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    previous_order: int | None = None
    previous_scene: int | None = None
    for block_id, scene_id, order_index, start_cp, end_cp in rows:
        contiguous = (
            current is not None
            and previous_order is not None
            and previous_scene == scene_id
            and order_index == previous_order + 1
        )
        if not contiguous:
            if current is not None:
                result.append(current)
            current = {
                "start_cp": int(start_cp),
                "end_cp": int(end_cp),
                "subject_ids": [int(block_id)],
            }
        else:
            assert current is not None
            current["end_cp"] = int(end_cp)
            subject_ids = current["subject_ids"]
            assert isinstance(subject_ids, list)
            subject_ids.append(int(block_id))
        previous_order = int(order_index)
        previous_scene = None if scene_id is None else int(scene_id)
    if current is not None:
        result.append(current)
    return result


def _effective_exposition_blocks(
    connection: sqlite3.Connection,
    structure_id: int,
    target_type: str,
    target_id: int,
    metric_run_id: int,
) -> list[dict[str, object]]:
    block_run_id = _metric_dependencies(connection, metric_run_id).get(
        "block-semantic-classifier"
    )
    if block_run_id is None:
        return []
    blocks = _scope_blocks(connection, structure_id, target_type, target_id)
    annotations = load_annotations(connection, block_run_id, "block.semantic_primary")
    threshold = AnalysisPolicy().block_semantic_effective
    result: list[dict[str, object]] = []
    for block in blocks:
        if block.block_type != "narration":
            continue
        effective = resolve_block_semantic(
            connection,
            block.id,
            block_run_id,
            annotations.get(block.id),
            threshold,
        )
        if effective.value == "exposition":
            result.append(
                {
                    "subject_id": block.id,
                    "start_cp": block.start_cp,
                    "end_cp": block.end_cp,
                }
            )
    return sorted(result, key=lambda item: (-_span_length(item), item["subject_id"]))


def _first_appearance_mentions(
    connection: sqlite3.Connection,
    document_id: int,
    text_revision_id: int,
    structure_id: int,
    target_type: str,
    target_id: int,
    metric_run_id: int,
) -> list[dict[str, object]]:
    term_run_id = _metric_dependencies(connection, metric_run_id).get("term-resolver")
    if term_run_id is None:
        return []
    resolver = CurrentRunResolver(connection)
    entries, complete = resolver.term_prefix(
        document_id, text_revision_id, structure_id, term_run_id
    )
    if not complete:
        return []
    repository = TermRepository(connection)
    first_by_term: dict[int, tuple[tuple[int, int, int], TermMentionRecord]] = {}
    current_mentions: dict[int, TermMentionRecord] = {}
    for entry in entries:
        if entry.term_run_id is None or entry.document_id is None:
            continue
        novelty = {
            subject_id: resolve_term_novelty(
                connection,
                subject_id,
                entry.term_run_id,
                (subject_id, value_json, confidence, start_cp),
            ).value
            for subject_id, value_json, confidence, start_cp in annotation_records(
                connection, entry.term_run_id, "term.novelty"
            )
        }
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
    selected_mentions = sorted(
        (
            mention
            for _, mention in first_by_term.values()
            if mention.id in current_mentions
            and (target_type == "document" or mention.scene_id == target_id)
        ),
        key=lambda mention: (mention.start_cp, mention.id),
    )
    return [
        {
            "subject_id": mention.id,
            "start_cp": mention.start_cp,
            "end_cp": mention.end_cp,
        }
        for mention in selected_mentions
    ]


def _effective_explanation_spans(
    connection: sqlite3.Connection,
    document_id: int,
    text_revision_id: int,
    structure_id: int,
    target_type: str,
    target_id: int,
    metric_run_id: int,
) -> list[dict[str, object]]:
    explanation_run_id = _metric_dependencies(connection, metric_run_id).get(
        "term-explanation-detector"
    )
    if explanation_run_id is None:
        return []
    mentions = _first_appearance_mentions(
        connection,
        document_id,
        text_revision_id,
        structure_id,
        target_type,
        target_id,
        metric_run_id,
    )
    threshold = AnalysisPolicy().term_explanation_effective
    block_scenes = {
        int(row[0]): int(row[1])
        for row in connection.execute(
            "SELECT id, scene_id FROM style_blocks WHERE structure_revision_id = ?",
            (structure_id,),
        ).fetchall()
        if row[1] is not None
    }
    repository = TermRepository(connection)
    result: list[dict[str, object]] = []
    for mention_span in mentions:
        mention_id = mention_span["subject_id"]
        if not isinstance(mention_id, int):
            continue
        mention = repository.get_mention(mention_id)
        effective = resolve_term_mention_explanation(
            connection, mention.id, explanation_run_id, threshold
        )
        value = effective.value
        if not isinstance(value, dict):
            continue
        block_id = value.get("block_id")
        if (
            not isinstance(block_id, int)
            or block_scenes.get(block_id) != mention.scene_id
        ):
            continue
        item: dict[str, object] = {
            "subject_id": mention.id,
            "start_cp": mention.start_cp,
            "end_cp": mention.end_cp,
        }
        annotation_id = value.get("annotation_id")
        if isinstance(annotation_id, int):
            item["related_subject_id"] = annotation_id
            row = connection.execute(
                "SELECT start_cp, end_cp FROM style_annotations WHERE id = ?",
                (annotation_id,),
            ).fetchone()
            if row is not None and row[0] is not None and row[1] is not None:
                item["related_start_cp"] = int(row[0])
                item["related_end_cp"] = int(row[1])
        result.append(item)
    return result


def _metric_dependencies(
    connection: sqlite3.Connection, metric_run_id: int
) -> dict[str, int]:
    run = AnalysisRunRepository(connection).get_run(metric_run_id)
    if run is None or run.analyzer_id != "style-metrics-semantic":
        return {}
    return {analyzer_id: run_id for analyzer_id, run_id in run.dependency_runs}


def _scope_blocks(
    connection: sqlite3.Connection, structure_id: int, target_type: str, target_id: int
) -> tuple[BlockRecord, ...]:
    rows = connection.execute(
        "SELECT id, structure_revision_id, scene_id, order_index, paragraph_index, "
        "block_type, start_cp, end_cp FROM style_blocks "
        "WHERE structure_revision_id = ? AND "
        "(? = 'document' OR scene_id = ?) ORDER BY order_index, id",
        (structure_id, target_type, target_id),
    ).fetchall()
    return tuple(BlockRecord(*row) for row in rows)


def _span_length(span: dict[str, object]) -> int:
    start = span.get("start_cp")
    end = span.get("end_cp")
    return (
        int(end) - int(start) if isinstance(start, int) and isinstance(end, int) else 0
    )


def canonical_evidence_json(evidence_json: str) -> str | None:
    try:
        value = json.loads(evidence_json)
    except (TypeError, json.JSONDecodeError, ValueError):
        return None
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
