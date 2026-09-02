from __future__ import annotations

import json
from typing import cast


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
        str(raw.get("reason_code", reason)),
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
    if isinstance(value, dict):
        return value.get(key)
    return value if key == "value" else None


def json_field(value_json: object, key: str) -> object:
    try:
        value = json.loads(cast(str, value_json))
    except (TypeError, json.JSONDecodeError):
        return None
    if isinstance(value, dict):
        return value.get(key)
    return value if key in {"value", "label", "speaker_entity_id"} else None


def confidence(value: object) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )
