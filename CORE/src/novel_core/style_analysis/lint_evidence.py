from __future__ import annotations

import json
import sqlite3


def build_lint_evidence(
    connection: sqlite3.Connection,
    *,
    metric_name: str,
    target_type: str,
    target_id: int,
    text_revision_id: int,
    structure_revision_id: int,
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
    elif metric_name == "semantic.exposition.char_ratio":
        spans = _exposition_blocks(
            connection, structure_revision_id, target_type, target_id
        )
        kind = "exposition_block"
    elif metric_name == "term.new_per_1000_chars":
        spans = _term_mentions(
            connection, structure_revision_id, target_type, target_id
        )
        kind = "term_first_appearance"
    elif metric_name.startswith("term.explanation_delay."):
        spans = _term_explanations(
            connection, structure_revision_id, target_type, target_id
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


def _exposition_blocks(
    connection: sqlite3.Connection, structure_id: int, target_type: str, target_id: int
) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT a.subject_id, b.start_cp, b.end_cp "
        "FROM style_annotations AS a "
        "JOIN style_analysis_runs AS r ON r.id = a.analysis_run_id "
        "JOIN style_blocks AS b ON b.id = a.subject_id "
        "WHERE r.structure_revision_id = ? "
        "AND r.analyzer_id = 'block-semantic-classifier' "
        "AND r.status = 'succeeded' AND a.annotation_type = 'block.semantic_primary' "
        "AND a.subject_type = 'block' "
        "AND json_extract(a.value_json, '$.label') = 'exposition' "
        "AND b.structure_revision_id = ? AND (? = 'document' OR b.scene_id = ?) "
        "ORDER BY (b.end_cp - b.start_cp) DESC, b.id",
        (structure_id, structure_id, target_type, target_id),
    ).fetchall()
    return [
        {
            "subject_id": int(subject_id),
            "start_cp": int(start_cp),
            "end_cp": int(end_cp),
        }
        for subject_id, start_cp, end_cp in rows[:5]
    ]


def _term_mentions(
    connection: sqlite3.Connection, structure_id: int, target_type: str, target_id: int
) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT id, start_cp, end_cp FROM style_term_mentions "
        "WHERE structure_revision_id = ? AND (? = 'document' OR scene_id = ?) "
        "ORDER BY start_cp, id LIMIT 5",
        (structure_id, target_type, target_id),
    ).fetchall()
    return [
        {
            "subject_id": int(subject_id),
            "start_cp": int(start_cp),
            "end_cp": int(end_cp),
        }
        for subject_id, start_cp, end_cp in rows
    ]


def _term_explanations(
    connection: sqlite3.Connection, structure_id: int, target_type: str, target_id: int
) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT m.id, m.start_cp, m.end_cp, a.id, a.start_cp, a.end_cp "
        "FROM style_term_mentions AS m "
        "JOIN style_annotations AS a ON a.subject_type = 'term_mention' "
        "AND a.subject_id = m.id AND a.annotation_type = 'term_explanation' "
        "JOIN style_analysis_runs AS r ON r.id = a.analysis_run_id "
        "WHERE m.structure_revision_id = ? AND r.structure_revision_id = ? "
        "AND r.status = 'succeeded' "
        "AND json_extract(a.value_json, '$.completeness') = 'sufficient' "
        "AND (? = 'document' OR m.scene_id = ?) "
        "ORDER BY m.start_cp, m.id LIMIT 5",
        (structure_id, structure_id, target_type, target_id),
    ).fetchall()
    result: list[dict[str, object]] = []
    for mention_id, mention_start, mention_end, annotation_id, start_cp, end_cp in rows:
        item: dict[str, object] = {
            "subject_id": int(mention_id),
            "start_cp": int(mention_start),
            "end_cp": int(mention_end),
            "related_subject_id": int(annotation_id),
        }
        if start_cp is not None and end_cp is not None:
            item["related_start_cp"] = int(start_cp)
            item["related_end_cp"] = int(end_cp)
        result.append(item)
    return result


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
