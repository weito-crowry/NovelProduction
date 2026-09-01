from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean, median, pstdev
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.aggregate_repository import json_object
from novel_core.style_analysis.corpus_models import (
    AggregateSpec,
    MeasurementTargetType,
    Statistic,
)
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.metrics import BASIC_METRIC_DEFINITIONS, percentile
from novel_core.style_analysis.semantic_models import (
    SCENE_FUNCTIONS,
    SCENE_INFORMATION_LOADS,
    SCENE_INTERACTIONS,
    SCENE_PACES,
    SCENE_TONES,
)

_SCENE_AXES = frozenset({"function", "tone", "pace", "information_load", "interaction"})
_SCENE_AXIS_LABELS = {
    "function": SCENE_FUNCTIONS,
    "tone": SCENE_TONES,
    "pace": SCENE_PACES,
    "information_load": SCENE_INFORMATION_LOADS,
    "interaction": SCENE_INTERACTIONS,
}


@dataclass(frozen=True, slots=True)
class _Target:
    identity: tuple[object, ...]
    measurement_id: int | None
    value: float | None
    sample_count: int
    work_id: int
    filter_result: str
    filter_state: tuple[dict[str, JsonValue], ...]


_STATISTICS: tuple[Statistic, ...] = (
    "mean",
    "median",
    "p10",
    "p25",
    "p75",
    "p90",
    "stddev",
    "min",
    "max",
)


def _parse_filter(
    filter_json: str, target_type: MeasurementTargetType
) -> dict[str, list[str]]:
    try:
        value = json.loads(filter_json)
    except json.JSONDecodeError as exc:
        raise ValidationError("AGGREGATE_FILTER_INVALID") from exc
    if not isinstance(value, dict):
        raise ValidationError("AGGREGATE_FILTER_INVALID")
    if target_type not in {"document", "scene"}:
        raise ValidationError("AGGREGATE_TARGET_INVALID")
    if target_type == "document":
        if value != {}:
            raise ValidationError("DOCUMENT_FILTER_NOT_ALLOWED")
        return {}
    if set(value) - {"scene"}:
        raise ValidationError("AGGREGATE_FILTER_INVALID")
    scene = value.get("scene", {})
    if not isinstance(scene, dict) or set(scene) - _SCENE_AXES:
        raise ValidationError("AGGREGATE_FILTER_INVALID")
    parsed: dict[str, list[str]] = {}
    for axis, labels in scene.items():
        if (
            not isinstance(labels, list)
            or not labels
            or any(not isinstance(label, str) for label in labels)
            or any(label not in _SCENE_AXIS_LABELS[axis] for label in labels)
            or ("unclear" in labels and len(set(labels)) != 1)
        ):
            raise ValidationError("AGGREGATE_FILTER_INVALID")
        parsed[axis] = sorted(set(labels))
    return parsed


def _canonical_filter_json(filter_json: str, target_type: MeasurementTargetType) -> str:
    _parse_filter(filter_json, target_type)
    return json_object(json.loads(filter_json))


def _metric_version(metric_name: str) -> int:
    definition = BASIC_METRIC_DEFINITIONS.get(metric_name)
    if definition is None:
        raise ValidationError("METRIC_NOT_FOUND")
    return definition.version


def _effective_axis_values(
    axis: str, annotation: tuple[object, object] | None
) -> tuple[list[str] | None, str]:
    if annotation is None:
        return None, "unknown"
    raw_value, raw_confidence = annotation
    confidence = (
        float(raw_confidence) if isinstance(raw_confidence, (int, float)) else None
    )
    if confidence is None or confidence < 0.80:
        return ["unclear"], "inferred"
    try:
        value = json.loads(cast(str, raw_value))
    except (TypeError, json.JSONDecodeError):
        return ["unclear"], "inferred"
    if axis in {"function", "tone"}:
        labels = value.get("labels") if isinstance(value, dict) else None
        accepted = (
            [
                str(item["label"])
                for item in labels
                if isinstance(item, dict)
                and isinstance(item.get("label"), str)
                and item.get("label") != "unclear"
                and isinstance(item.get("confidence", confidence), (int, float))
                and float(item.get("confidence", confidence)) >= 0.80
            ]
            if isinstance(labels, list)
            else []
        )
        return (sorted(set(accepted)) or ["unclear"]), "inferred"
    label = value.get("label") if isinstance(value, dict) else None
    return ([label] if isinstance(label, str) else ["unclear"]), "inferred"


def _filter_state_fingerprint(
    targets: tuple[_Target, ...] | list[_Target],
) -> str | None:
    state = [item for target in targets for item in target.filter_state]
    return (
        None
        if not state
        else fingerprint_json(cast(JsonValue, sorted(state, key=json_object)))
    )


def _input_fingerprint(
    policy_version: int,
    spec: AggregateSpec,
    targets: tuple[_Target, ...] | list[_Target],
    statistic: Statistic,
    *,
    source_episode_ids: tuple[int, ...] | None = None,
) -> str:
    payload: JsonValue = {
        "aggregate_policy_version": policy_version,
        "container_type": spec.container_type,
        "container_id": spec.container_id,
        "measurement_target_type": spec.measurement_target_type,
        "filter_json": json.loads(spec.filter_json),
        "metric_name": spec.metric_name,
        "metric_version": spec.metric_version,
        "statistic": statistic,
        "source_episode_ids": cast(
            JsonValue,
            sorted(
                source_episode_ids
                if source_episode_ids is not None
                else (
                    int(cast(int, target.identity[1]))
                    for target in targets
                    if target.identity
                )
            ),
        ),
        "candidate_targets": sorted(
            (
                {
                    "identity": cast(JsonValue, list(target.identity)),
                    "filter_result": target.filter_result,
                }
                for target in targets
            ),
            key=json_object,
        ),
        "input_measurement_ids": cast(
            JsonValue,
            sorted(
                target.measurement_id
                for target in targets
                if target.measurement_id is not None
            ),
        ),
        "filter_state_fingerprint": _filter_state_fingerprint(targets),
    }
    return fingerprint_json(payload)


def _statistic_value(
    statistic: Statistic, targets: tuple[_Target, ...] | list[_Target]
) -> float:
    values = [target.value for target in targets if target.value is not None]
    if not values:
        raise ValidationError("AGGREGATE_NO_VALUES")
    floats = [float(value) for value in values]
    if statistic == "mean":
        return float(mean(floats))
    if statistic == "median":
        return float(median(floats))
    if statistic in {"p10", "p25", "p75", "p90"}:
        quantile = {"p10": 0.10, "p25": 0.25, "p75": 0.75, "p90": 0.90}[statistic]
        return float(percentile(floats, quantile))
    if statistic == "stddev":
        return float(pstdev(floats))
    if statistic == "min":
        return float(min(floats))
    return float(max(floats))
