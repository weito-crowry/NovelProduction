from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from novel_core.style_analysis.semantic_lineage import current_mention_ids
from novel_core.style_analysis.semantic_values import (
    annotation_value,
    json_field,
    label_value,
    speaker_value,
)
from novel_core.style_analysis.semantic_values import (
    confidence as _confidence,
)
from novel_core.style_analysis.structure_models import BlockRecord


@dataclass(frozen=True, slots=True)
class EffectiveValue:
    value: object
    source: str
    confidence: float | None = None
    analysis_run_id: int | None = None
    override_id: int | None = None
    stale_override: bool = False


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
    result = resolve_block_semantic(connection, block_id, run_id, raw, threshold)
    return (
        result.value if isinstance(result.value, str) else None,
        result.source,
    )


def resolve_block_semantic(
    connection: sqlite3.Connection,
    block_id: int,
    run_id: int,
    raw: tuple[str, object, object] | None,
    threshold: float,
    *,
    include_manual: bool = True,
) -> EffectiveValue:
    override = (
        latest_override(connection, "block", block_id, "block.semantic_primary")
        if include_manual
        else None
    )
    if override is not None:
        override_id, operation, value_json = override
        if operation == "set":
            label = json_field(value_json, "label")
            if label is None:
                label = value_json if isinstance(value_json, str) else None
            return EffectiveValue(
                label if isinstance(label, str) else None,
                "manual" if isinstance(label, str) else "unknown",
                override_id=override_id,
            )
        return EffectiveValue(None, "manual", override_id=override_id)
    review = review_status(
        connection, "block", block_id, "block.semantic_primary", run_id
    )
    if review == "rejected":
        return EffectiveValue(None, "unknown", analysis_run_id=run_id)
    label, confidence, _ = label_value(raw)
    if label is None:
        return EffectiveValue(None, "unknown", confidence, run_id)
    if review == "confirmed" or confidence >= threshold:
        return EffectiveValue(
            label,
            "confirmed" if review == "confirmed" else "inferred",
            confidence=confidence,
            analysis_run_id=run_id,
        )
    return EffectiveValue(
        "unclear", "inferred", confidence=confidence, analysis_run_id=run_id
    )


def effective_speaker(
    connection: sqlite3.Connection,
    block_id: int,
    run_id: int,
    raw: tuple[str, object, object] | None,
    threshold: float,
) -> int | None:
    result = resolve_speaker(connection, block_id, run_id, raw, threshold)
    return result.value if isinstance(result.value, int) else None


def resolve_speaker(
    connection: sqlite3.Connection,
    block_id: int,
    run_id: int,
    raw: tuple[str, object, object] | None,
    threshold: float,
    *,
    include_manual: bool = True,
) -> EffectiveValue:
    override = (
        latest_override(connection, "block", block_id, "block.speaker_entity_id")
        if include_manual
        else None
    )
    if override is not None:
        override_id, operation, value_json = override
        if operation == "clear":
            return EffectiveValue(None, "manual", override_id=override_id)
        if operation == "set":
            value = json_field(value_json, "speaker_entity_id")
            if not (
                isinstance(value, int)
                and not isinstance(value, bool)
                and enabled_person(connection, value)
            ):
                return EffectiveValue(None, "unknown", override_id=override_id)
            return EffectiveValue(
                value,
                "manual",
                override_id=override_id,
            )
    review = review_status(connection, "block", block_id, "block.speaker", run_id)
    if review == "rejected":
        return EffectiveValue(None, "unknown", analysis_run_id=run_id)
    entity_id, confidence, reason = speaker_value(raw)
    if entity_id is None:
        return EffectiveValue(
            None, "unknown", confidence=confidence, analysis_run_id=run_id
        )
    if not enabled_person(connection, entity_id):
        return EffectiveValue(
            None, "unknown", confidence=confidence, analysis_run_id=run_id
        )
    if review == "confirmed":
        return EffectiveValue(
            entity_id, "confirmed", confidence=confidence, analysis_run_id=run_id
        )
    if confidence < threshold or reason == "turn_taking":
        return EffectiveValue(
            None, "unknown", confidence=confidence, analysis_run_id=run_id
        )
    return EffectiveValue(
        entity_id, "inferred", confidence=confidence, analysis_run_id=run_id
    )


def effective_novelty(
    connection: sqlite3.Connection,
    term_id: int,
    run_id: int,
    raw: tuple[int, str, object, object],
) -> object:
    return resolve_term_novelty(connection, term_id, run_id, raw).value


def resolve_term_novelty(
    connection: sqlite3.Connection,
    term_id: int,
    run_id: int,
    raw: tuple[int, str, object, object] | None,
    *,
    include_manual: bool = True,
) -> EffectiveValue:
    override = (
        latest_override(connection, "term", term_id, "term.novelty")
        if include_manual
        else None
    )
    if override is not None:
        override_id, operation, value_json = override
        if operation == "clear":
            return EffectiveValue(None, "manual", override_id=override_id)
        if operation == "set":
            return EffectiveValue(
                json_field(value_json, "value"), "manual", override_id=override_id
            )
    review = review_status(connection, "term", term_id, "term.novelty", run_id)
    if review == "rejected":
        return EffectiveValue(None, "unknown", analysis_run_id=run_id)
    if raw is None:
        return EffectiveValue("uncertain", "default")
    value = annotation_value(raw[1], "value")
    if not isinstance(value, str):
        return EffectiveValue(
            None, "unknown", confidence=_confidence(raw[2]), analysis_run_id=run_id
        )
    return EffectiveValue(
        value,
        "confirmed" if review == "confirmed" else "inferred",
        confidence=_confidence(raw[2]),
        analysis_run_id=run_id,
    )


def resolve_entity_enabled(
    connection: sqlite3.Connection, entity_id: int
) -> EffectiveValue:
    from novel_core.style_analysis.semantic_effective import (
        resolve_entity_enabled as impl,
    )

    return impl(connection, entity_id)


def resolve_entity_name(
    connection: sqlite3.Connection, entity_id: int
) -> EffectiveValue:
    from novel_core.style_analysis.semantic_effective import resolve_entity_name as impl

    return impl(connection, entity_id)


def resolve_entity_type(
    connection: sqlite3.Connection, entity_id: int
) -> EffectiveValue:
    from novel_core.style_analysis.semantic_effective import resolve_entity_type as impl

    return impl(connection, entity_id)


def resolve_term_enabled(
    connection: sqlite3.Connection, term_id: int
) -> EffectiveValue:
    from novel_core.style_analysis.semantic_effective import (
        resolve_term_enabled as impl,
    )

    return impl(connection, term_id)


def resolve_term_label(connection: sqlite3.Connection, term_id: int) -> EffectiveValue:
    from novel_core.style_analysis.semantic_effective import resolve_term_label as impl

    return impl(connection, term_id)


def resolve_term_type(connection: sqlite3.Connection, term_id: int) -> EffectiveValue:
    from novel_core.style_analysis.semantic_effective import resolve_term_type as impl

    return impl(connection, term_id)


def resolve_mention_entity(
    connection: sqlite3.Connection,
    mention_id: int,
    run_id: int,
    raw: tuple[str, object, object] | None,
    *,
    include_manual: bool = True,
) -> EffectiveValue:
    override = (
        latest_override(connection, "mention", mention_id, "mention.entity_id")
        if include_manual
        else None
    )
    if override is not None:
        override_id, operation, value_json = override
        if operation == "clear":
            return EffectiveValue(None, "manual", override_id=override_id)
        if operation == "set":
            value = json_field(value_json, "value")
            return EffectiveValue(
                value
                if isinstance(value, int) and not isinstance(value, bool)
                else None,
                "manual",
                override_id=override_id,
            )
    review = review_status(
        connection, "mention", mention_id, "mention.entity_resolution", run_id
    )
    if review == "rejected":
        return EffectiveValue(None, "unknown", analysis_run_id=run_id)
    value = annotation_value(raw[0], "entity_id") if raw is not None else None
    return EffectiveValue(
        value if isinstance(value, int) and not isinstance(value, bool) else None,
        "confirmed"
        if review == "confirmed"
        else "inferred"
        if raw is not None
        else "unknown",
        confidence=_confidence(raw[1]) if raw is not None else None,
        analysis_run_id=run_id,
    )


def resolve_term_mention_explanation(
    connection: sqlite3.Connection,
    mention_id: int,
    explanation_run_id: int | None,
    threshold: float,
    *,
    include_manual: bool = True,
) -> EffectiveValue:
    override = (
        latest_override(
            connection,
            "term_mention",
            mention_id,
            "term_mention.sufficient_explanation_annotation_id",
        )
        if include_manual
        else None
    )
    if override is not None:
        override_id, operation, value_json = override
        if operation == "clear":
            return EffectiveValue(None, "manual", override_id=override_id)
        if operation == "set":
            annotation_id = json_field(value_json, "value")
            if isinstance(annotation_id, int) and not isinstance(annotation_id, bool):
                row = connection.execute(
                    "SELECT value_json, confidence, analysis_run_id, start_cp "
                    "FROM style_annotations WHERE id = ?",
                    (annotation_id,),
                ).fetchone()
                if row is not None and _is_sufficient_explanation(row[0]):
                    return EffectiveValue(
                        {
                            "annotation_id": annotation_id,
                            "block_id": _json_field(row[0], "block_id"),
                            "start_cp": row[3],
                        },
                        "manual",
                        confidence=_confidence(row[1]),
                        analysis_run_id=int(row[2]),
                        override_id=override_id,
                    )
            return EffectiveValue(None, "manual", override_id=override_id)
    if explanation_run_id is None:
        return EffectiveValue(None, "unknown")
    row = connection.execute(
        "SELECT id, value_json, confidence, start_cp FROM style_annotations "
        "WHERE analysis_run_id = ? AND annotation_type = 'term_explanation' "
        "AND subject_type = 'term_mention' AND subject_id = ?",
        (explanation_run_id, mention_id),
    ).fetchone()
    if row is None:
        return EffectiveValue(None, "unknown", analysis_run_id=explanation_run_id)
    review = review_status(
        connection,
        "term_mention",
        mention_id,
        "term_mention.explanation",
        explanation_run_id,
    )
    if review == "rejected":
        return EffectiveValue(None, "unknown", analysis_run_id=explanation_run_id)
    sufficient = _is_sufficient_explanation(row[1])
    confidence = _confidence(row[2])
    if not sufficient or (review != "confirmed" and (confidence or 0.0) < threshold):
        return EffectiveValue(
            None, "unknown", confidence=confidence, analysis_run_id=explanation_run_id
        )
    return EffectiveValue(
        {
            "annotation_id": int(row[0]),
            "block_id": _json_field(row[1], "block_id"),
            "start_cp": row[3],
        },
        "confirmed" if review == "confirmed" else "inferred",
        confidence=confidence,
        analysis_run_id=explanation_run_id,
    )


def _is_sufficient_explanation(value_json: object) -> bool:
    return _json_field(value_json, "completeness") == "sufficient"


def _json_field(value_json: object, key: str) -> object:
    try:
        value = json.loads(cast(str, value_json))
    except (TypeError, json.JSONDecodeError):
        return None
    return value.get(key) if isinstance(value, dict) else None


def latest_override(
    connection: sqlite3.Connection,
    subject_type: str,
    subject_id: int,
    field_path: str,
) -> tuple[int, str, object] | None:
    from novel_core.style_analysis.semantic_overrides import latest_override as impl

    return impl(connection, subject_type, subject_id, field_path)


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


def eligible_persons(
    connection: sqlite3.Connection,
    speaker_run_id: int,
    *,
    blocks: Sequence[BlockRecord] = (),
    entity_run_id: int | None = None,
    threshold: float = 0.85,
) -> set[int]:
    resolver = connection.execute(
        "SELECT links.dependency_run_id FROM style_analysis_run_dependencies links "
        "JOIN style_analysis_runs dep ON dep.id = links.dependency_run_id "
        "WHERE links.run_id = ? AND dep.analyzer_id = 'entity-resolver' "
        "ORDER BY links.dependency_run_id DESC LIMIT 1",
        (speaker_run_id,),
    ).fetchone()
    annotation_run_id = (
        entity_run_id
        if entity_run_id is not None
        else int(resolver[0])
        if resolver is not None
        else speaker_run_id
    )
    result: set[int] = set()
    mention_rows = connection.execute(
        "SELECT subject_id, value_json, confidence FROM style_annotations "
        "WHERE analysis_run_id = ? AND annotation_type = 'mention.entity_resolution'",
        (annotation_run_id,),
    ).fetchall()
    raw_by_mention = {
        int(subject_id): (str(value_json), confidence, None)
        for subject_id, value_json, confidence in mention_rows
    }
    structure_row = connection.execute(
        "SELECT structure_revision_id FROM style_analysis_runs WHERE id = ?",
        (annotation_run_id,),
    ).fetchone()
    mention_ids = (
        current_mention_ids(connection, annotation_run_id, int(structure_row[0]))
        if structure_row is not None
        else frozenset()
    )
    for subject_id in mention_ids:
        raw = raw_by_mention.get(subject_id)
        entity_id = resolve_mention_entity(
            connection,
            subject_id,
            annotation_run_id,
            raw,
        ).value
        if (
            isinstance(entity_id, int)
            and not isinstance(entity_id, bool)
            and enabled_person(connection, entity_id)
        ):
            result.add(entity_id)
    speaker_annotations = load_annotations(connection, speaker_run_id, "speaker")
    for block in blocks:
        if block.block_type != "dialogue":
            continue
        entity_id = resolve_speaker(
            connection,
            block.id,
            speaker_run_id,
            speaker_annotations.get(block.id),
            threshold,
        ).value
        if (
            isinstance(entity_id, int)
            and not isinstance(entity_id, bool)
            and enabled_person(connection, entity_id)
        ):
            result.add(entity_id)
    return result


def enabled_person(connection: sqlite3.Connection, entity_id: int) -> bool:
    if resolve_entity_type(connection, entity_id).value != "person":
        return False
    override = latest_override(connection, "entity", entity_id, "entity.enabled")
    if override is None or override[1] != "set":
        return True
    return json_field(override[2], "value") is not False


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
