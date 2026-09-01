from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

from novel_core.style_analysis.semantic_metric_support import (
    EffectiveValue,
    latest_override,
    review_status,
)
from novel_core.style_analysis.semantic_values import confidence

RawSceneAnnotations = Mapping[str, tuple[object, object, object] | None]

_SCENE_AXES = (
    "scene.function",
    "scene.tone",
    "scene.pace",
    "scene.information_load",
    "scene.interaction",
)


def resolve_scene_semantics(
    connection: sqlite3.Connection,
    scene_id: int,
    run_id: int | None,
    raw_annotations: RawSceneAnnotations,
    *,
    structure_revision_id: int,
    scene_threshold: float = 0.80,
    pov_threshold: float = 0.80,
) -> dict[str, EffectiveValue]:
    resolved = {
        annotation_type: _resolve_axis(
            connection,
            scene_id,
            annotation_type,
            run_id,
            raw_annotations.get(annotation_type),
            structure_revision_id,
            scene_threshold,
        )
        for annotation_type in _SCENE_AXES
    }
    resolved["scene.pov"] = _resolve_pov(
        connection,
        scene_id,
        run_id,
        raw_annotations.get("scene.pov"),
        structure_revision_id,
        pov_threshold,
    )
    return resolved


def scene_axis_values(axis: str, value: object) -> list[str] | None:
    if not isinstance(value, dict):
        return None
    if axis in {"function", "tone"}:
        labels = value.get("labels")
        if not isinstance(labels, list):
            return None
        return [
            str(item["label"])
            for item in labels
            if isinstance(item, dict) and isinstance(item.get("label"), str)
        ]
    label = value.get("label")
    return [label] if isinstance(label, str) else None


def _resolve_axis(
    connection: sqlite3.Connection,
    scene_id: int,
    annotation_type: str,
    run_id: int | None,
    raw: tuple[object, object, object] | None,
    structure_revision_id: int,
    threshold: float,
) -> EffectiveValue:
    field_path = annotation_type
    override, stale = _current_override(
        connection, scene_id, field_path, structure_revision_id
    )
    if override is not None:
        operation = override[1]
        if operation == "clear":
            return EffectiveValue(None, "manual", override_id=override[0])
        value = _decode(override[2])
        if annotation_type in {"scene.function", "scene.tone"}:
            labels = value if isinstance(value, list) else []
            value = {
                "labels": [{"label": item} for item in labels if isinstance(item, str)]
            }
        else:
            value = {"label": value}
        return EffectiveValue(
            value,
            "manual",
            override_id=override[0],
            stale_override=stale,
        )
    raw_value, raw_confidence = _raw_value(raw)
    review = (
        review_status(connection, "scene", scene_id, annotation_type, run_id)
        if run_id is not None
        else None
    )
    if raw_value is None:
        return EffectiveValue(None, "unknown", stale_override=stale)
    confidence_value = confidence(raw_confidence)
    if review == "rejected":
        return EffectiveValue(
            None, "unknown", analysis_run_id=run_id, stale_override=stale
        )
    if review != "confirmed" and (
        confidence_value is None or confidence_value < threshold
    ):
        value = _unclear_value(annotation_type, confidence_value)
    else:
        value = _normalize_raw(
            annotation_type,
            raw_value,
            confidence_value,
            threshold,
            confirmed=review == "confirmed",
        )
        if value is None:
            return EffectiveValue(
                None,
                "unknown",
                confidence=confidence_value,
                analysis_run_id=run_id,
                stale_override=stale,
            )
    return EffectiveValue(
        value,
        "confirmed" if review == "confirmed" else "inferred",
        confidence=confidence_value,
        analysis_run_id=run_id,
        stale_override=stale,
    )


def _resolve_pov(
    connection: sqlite3.Connection,
    scene_id: int,
    run_id: int | None,
    raw: tuple[object, object, object] | None,
    structure_revision_id: int,
    threshold: float,
) -> EffectiveValue:
    base = _resolve_axis(
        connection,
        scene_id,
        "scene.pov",
        run_id,
        raw,
        structure_revision_id,
        threshold,
    )
    if base.source == "unknown" and base.value is None:
        base_value: dict[str, object] = {}
    elif isinstance(base.value, dict):
        base_value = dict(base.value)
    else:
        base_value = {}
    applied = base.override_id
    stale = base.stale_override
    mode_override, mode_stale = _current_override(
        connection, scene_id, "scene.pov_mode", structure_revision_id
    )
    entity_override, entity_stale = _current_override(
        connection, scene_id, "scene.pov_entity_id", structure_revision_id
    )
    stale = stale or mode_stale or entity_stale
    if mode_override is not None:
        applied = mode_override[0]
        base_value["pov_mode"] = _decode(mode_override[2])
    if entity_override is not None:
        applied = entity_override[0]
        entity_id = _decode(entity_override[2])
        base_value["pov_entity_id"] = _enabled_person_or_none(connection, entity_id)
    elif "pov_entity_id" in base_value:
        base_value["pov_entity_id"] = _enabled_person_or_none(
            connection, base_value["pov_entity_id"]
        )
    if mode_override is not None or entity_override is not None:
        return EffectiveValue(
            base_value,
            "manual",
            confidence=base.confidence,
            analysis_run_id=base.analysis_run_id,
            override_id=applied,
            stale_override=stale,
        )
    if base.value is not None and isinstance(base.value, dict):
        return EffectiveValue(
            base_value,
            base.source,
            confidence=base.confidence,
            analysis_run_id=base.analysis_run_id,
            override_id=base.override_id,
            stale_override=stale,
        )
    return base


def _current_override(
    connection: sqlite3.Connection,
    scene_id: int,
    field_path: str,
    structure_revision_id: int,
) -> tuple[tuple[int, str, object] | None, bool]:
    row = latest_override(connection, "scene", scene_id, field_path)
    if row is None:
        return None, False
    structure = connection.execute(
        "SELECT structure_revision_id FROM style_manual_overrides WHERE id = ?",
        (row[0],),
    ).fetchone()
    stale = (
        structure is not None
        and structure[0] is not None
        and int(structure[0]) != structure_revision_id
    )
    return (None, True) if stale else (row, False)


def _raw_value(
    raw: tuple[object, object, object] | None,
) -> tuple[object | None, object | None]:
    if raw is None:
        return None, None
    try:
        return json.loads(str(raw[0])), raw[1]
    except (TypeError, json.JSONDecodeError):
        return None, raw[1]


def _decode(value: object) -> object:
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return None


def _normalize_raw(
    annotation_type: str,
    value: object,
    confidence_value: float | None,
    threshold: float,
    *,
    confirmed: bool = False,
) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    if annotation_type in {"scene.function", "scene.tone"}:
        labels = value.get("labels")
        if not isinstance(labels, list):
            return None
        accepted = [
            dict(item)
            for item in labels
            if isinstance(item, dict)
            and item.get("label") != "unclear"
            and isinstance(item.get("label"), str)
            and (
                confirmed
                or (
                    confidence_value is None
                    or (confidence(item.get("confidence", confidence_value)) or 0.0)
                    >= threshold
                )
            )
        ]
        return {
            "labels": accepted or [{"label": "unclear", "confidence": confidence_value}]
        }
    if annotation_type == "scene.pov":
        return dict(value)
    label = value.get("label")
    return {"label": label} if isinstance(label, str) else None


def _unclear_value(
    annotation_type: str, confidence_value: float | None
) -> dict[str, object]:
    if annotation_type in {"scene.function", "scene.tone"}:
        return {"labels": [{"label": "unclear", "confidence": confidence_value}]}
    if annotation_type == "scene.pov":
        return {"pov_mode": "unclear", "pov_entity_id": None}
    return {"label": "unclear"}


def _enabled_person_or_none(
    connection: sqlite3.Connection, value: object
) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    from novel_core.style_analysis.semantic_metric_support import enabled_person

    return value if enabled_person(connection, value) else None
