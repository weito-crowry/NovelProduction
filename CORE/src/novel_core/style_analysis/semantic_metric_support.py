from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from typing import cast

from novel_core.style_analysis.structure_models import BlockRecord


def load_annotations(
    connection: sqlite3.Connection, run_id: int, annotation_type: str
) -> dict[int, tuple[str, object, object]]:
    return {
        int(row[0]): (str(row[1]), row[2], row[3])
        for row in connection.execute(
            "SELECT subject_id, value_json, confidence, "
            "json_extract(value_json, '$.source') "
            "FROM style_annotations WHERE analysis_run_id = ? "
            "AND annotation_type = ?",
            (run_id, annotation_type),
        )
    }


def annotation_records(
    connection: sqlite3.Connection, run_id: int | None, annotation_type: str
) -> tuple[tuple[int, str, object, object], ...]:
    if run_id is None:
        return ()
    return tuple(
        (int(row[0]), str(row[1]), row[2], row[3])
        for row in connection.execute(
            "SELECT subject_id, value_json, confidence, start_cp "
            "FROM style_annotations WHERE analysis_run_id = ? "
            "AND annotation_type = ?",
            (run_id, annotation_type),
        ).fetchall()
    )


def effective_block_label(
    connection: sqlite3.Connection,
    block_id: int,
    run_id: int,
    raw: tuple[str, object, object] | None,
    threshold: float,
) -> tuple[str | None, str]:
    override = latest_override(connection, "block", block_id, "block.semantic_primary")
    if override is not None:
        operation, value_json = override
        if operation == "set":
            label = json_field(value_json, "label")
            if label is None and isinstance(value_json, str):
                label = value_json
            return (
                label if isinstance(label, str) else None,
                "manual" if isinstance(label, str) else "unknown",
            )
    review = review_status(
        connection, "block", block_id, "block.semantic_primary", run_id
    )
    if review == "rejected":
        return None, "unknown"
    label, confidence, _ = label_value(raw)
    if label is None:
        return None, "unknown"
    if review == "confirmed" or confidence >= threshold:
        return label, "inferred"
    return "unclear", "inferred"


def effective_speaker(
    connection: sqlite3.Connection,
    block_id: int,
    run_id: int,
    raw: tuple[str, object, object] | None,
    threshold: float,
) -> int | None:
    override = latest_override(connection, "block", block_id, "block.speaker")
    if override is not None:
        operation, value_json = override
        if operation != "set":
            return None
        value = json_field(value_json, "speaker_entity_id")
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    review = review_status(connection, "block", block_id, "block.speaker", run_id)
    if review == "rejected":
        return None
    entity_id, confidence, reason = speaker_value(raw)
    if entity_id is None or confidence < threshold:
        return None
    if reason == "turn_taking" and review != "confirmed":
        return None
    return entity_id


def effective_novelty(
    connection: sqlite3.Connection,
    term_id: int,
    run_id: int,
    raw: tuple[int, str, object, object],
) -> object:
    override = latest_override(connection, "term", term_id, "term.novelty")
    if override is not None:
        operation, value_json = override
        if operation != "set":
            return None
        return json_field(value_json, "value")
    review = review_status(connection, "term", term_id, "term.novelty", run_id)
    if review == "rejected":
        return None
    return annotation_value(raw[1], "value")


def speaker_value(
    value: tuple[str, object, object] | None,
) -> tuple[int | None, float, str]:
    if value is None:
        return None, 0.0, "unknown"
    try:
        raw = json.loads(value[0])
    except (TypeError, json.JSONDecodeError):
        return None, 0.0, "unknown"
    entity_id = raw.get("speaker_entity_id") if isinstance(raw, dict) else None
    reason = raw.get("reason_code", "unknown") if isinstance(raw, dict) else "unknown"
    return (
        entity_id
        if isinstance(entity_id, int) and not isinstance(entity_id, bool)
        else None,
        float(value[1]) if isinstance(value[1], (int, float)) else 0.0,
        str(reason),
    )


def label_value(
    value: tuple[str, object, object] | None,
) -> tuple[str | None, float, str]:
    if value is None:
        return None, 0.0, "unknown"
    try:
        raw = json.loads(value[0])
    except (TypeError, json.JSONDecodeError):
        return None, 0.0, "unknown"
    label = raw.get("label") if isinstance(raw, dict) else None
    return (
        label if isinstance(label, str) else None,
        float(value[1]) if isinstance(value[1], (int, float)) else 0.0,
        str(value[2] or "inferred"),
    )


def annotation_value(value_json: object, key: str) -> object:
    try:
        value = json.loads(cast(str, value_json))
    except (TypeError, json.JSONDecodeError):
        return None
    return value.get(key) if isinstance(value, dict) else None


def json_field(value_json: object, key: str) -> object:
    try:
        value = json.loads(cast(str, value_json))
    except (TypeError, json.JSONDecodeError):
        return None
    if isinstance(value, dict):
        return value.get(key)
    return value if key in {"value", "label", "speaker_entity_id"} else None


def latest_override(
    connection: sqlite3.Connection,
    subject_type: str,
    subject_id: int,
    field_path: str,
) -> tuple[str, object] | None:
    row = connection.execute(
        "SELECT operation, value_json FROM style_manual_overrides "
        "WHERE subject_type = ? AND subject_id = ? AND field_path = ? "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (subject_type, subject_id, field_path),
    ).fetchone()
    return None if row is None else (str(row[0]), row[1])


def review_status(
    connection: sqlite3.Connection,
    subject_type: str,
    subject_id: int,
    field_path: str,
    run_id: int,
) -> str | None:
    row = connection.execute(
        "SELECT review_status FROM style_inference_reviews "
        "WHERE subject_type = ? AND subject_id = ? AND field_path = ? "
        "AND analysis_run_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (subject_type, subject_id, field_path, run_id),
    ).fetchone()
    return None if row is None else str(row[0])


def eligible_persons(connection: sqlite3.Connection, speaker_run_id: int) -> set[int]:
    resolver = connection.execute(
        "SELECT links.dependency_run_id FROM style_analysis_run_dependencies links "
        "JOIN style_analysis_runs dep ON dep.id = links.dependency_run_id "
        "WHERE links.run_id = ? AND dep.analyzer_id = 'entity-resolver' "
        "ORDER BY links.dependency_run_id DESC LIMIT 1",
        (speaker_run_id,),
    ).fetchone()
    annotation_run_id = resolver[0] if resolver is not None else speaker_run_id
    annotation_type = "mention.entity_resolution" if resolver is not None else "speaker"
    key = "entity_id" if resolver is not None else "speaker_entity_id"
    result: set[int] = set()
    rows = connection.execute(
        "SELECT value_json FROM style_annotations "
        "WHERE analysis_run_id = ? AND annotation_type = ?",
        (annotation_run_id, annotation_type),
    ).fetchall()
    for (value_json,) in rows:
        entity_id = annotation_value(value_json, key)
        if (
            isinstance(entity_id, int)
            and not isinstance(entity_id, bool)
            and enabled_person(connection, entity_id)
        ):
            result.add(entity_id)
    return result


def enabled_person(connection: sqlite3.Connection, entity_id: int) -> bool:
    row = connection.execute(
        "SELECT entity_type FROM style_entities WHERE id = ?", (entity_id,)
    ).fetchone()
    if row is None or row[0] != "person":
        return False
    override = latest_override(connection, "entity", entity_id, "entity.enabled")
    if override is None or override[0] != "set":
        return True
    return json_field(override[1], "value") is not False


def speaker_streaks(
    text: str,
    blocks: Sequence[BlockRecord],
    speaker_by_block: dict[int, int | None],
) -> dict[int, list[int]]:
    result: dict[int, list[int]] = defaultdict(list)
    previous_scene: int | None = None
    current_speaker: int | None = None
    current_length = 0

    def flush() -> None:
        nonlocal current_length, current_speaker
        if current_speaker is not None and current_length:
            result[current_speaker].append(current_length)
        current_speaker = None
        current_length = 0

    ordered = sorted(blocks, key=lambda item: (item.order_index, item.id))
    for index, block in enumerate(ordered):
        if block.scene_id != previous_scene:
            flush()
            previous_scene = block.scene_id
        if block.block_type == "dialogue":
            speaker = speaker_by_block.get(block.id)
            if speaker is None or speaker != current_speaker:
                flush()
                current_speaker = speaker
                current_length = 1 if speaker is not None else 0
            else:
                current_length += 1
            continue
        bridged = (
            block.block_type == "narration"
            and current_speaker is not None
            and _chars(text[block.start_cp : block.end_cp]) <= 40
            and index + 1 < len(ordered)
            and ordered[index + 1].block_type == "dialogue"
            and ordered[index + 1].scene_id == block.scene_id
        )
        if not bridged:
            flush()
    flush()
    return result


def is_question(value: str) -> bool:
    return _without_outer_quote(value).endswith(("?", "？"))


def utterance_length(value: str) -> int:
    return _chars(_without_outer_quote(value))


def _without_outer_quote(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[:1] in {"「", "『", '"'}:
        closing = {"「": "」", "『": "』", '"': '"'}[stripped[0]]
        if stripped.endswith(closing):
            return stripped[1:-1]
    return stripped


def _chars(value: str) -> int:
    return sum(not character.isspace() for character in value)
