from __future__ import annotations

import json
import math
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.aggregate_calculations import _input_fingerprint
from novel_core.style_analysis.aggregate_repository import AggregateRepository
from novel_core.style_analysis.aggregate_service import AggregateService
from novel_core.style_analysis.corpus_models import AggregateRecord, AggregateSpec
from novel_core.style_analysis.semantic_models import (
    SCENE_FUNCTIONS,
    SCENE_INFORMATION_LOADS,
    SCENE_INTERACTIONS,
    SCENE_PACES,
    SCENE_TONES,
)


def _with_staleness(
    repository: AggregateRepository, aggregate: AggregateRecord
) -> AggregateRecord:
    service = AggregateService(repository._connection)
    spec = AggregateSpec(
        aggregate.container_type,
        aggregate.container_id,
        aggregate.measurement_target_type,
        aggregate.filter_json,
        aggregate.metric_name,
        aggregate.metric_version,
    )
    values, _, source_episode_ids = service._compute(spec)
    current = _input_fingerprint(
        service.policy.version,
        spec,
        values,
        aggregate.statistic,
        source_episode_ids=source_episode_ids,
    )
    return AggregateRecord(
        **{
            field: getattr(aggregate, field)
            for field in aggregate.__dataclass_fields__
            if field != "stale"
        },
        stale=(
            aggregate.aggregate_policy_version != service.policy.version
            or aggregate.input_fingerprint != current
        ),
    )


def _rule_selector(aggregate: AggregateRecord) -> dict[str, object]:
    value = json.loads(aggregate.filter_json)
    if aggregate.measurement_target_type == "document":
        return {}
    scene = value.get("scene") if isinstance(value, dict) else None
    return dict(scene) if isinstance(scene, dict) else {}


def _validate_selector(target_scope: object, raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValidationError("PROFILE_SELECTOR_INVALID")
    if target_scope == "document" and raw:
        raise ValidationError("PROFILE_SELECTOR_INVALID")
    if target_scope == "document":
        return {}
    if target_scope == "scene":
        allowed = {"function", "tone", "pace", "information_load", "interaction"}
        labels_by_axis = {
            "function": SCENE_FUNCTIONS,
            "tone": SCENE_TONES,
            "pace": SCENE_PACES,
            "information_load": SCENE_INFORMATION_LOADS,
            "interaction": SCENE_INTERACTIONS,
        }
        if set(raw) - allowed or any(
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) for item in value)
            or any(item not in labels_by_axis[key] for item in value)
            or ("unclear" in value and len(set(value)) != 1)
            for key, value in raw.items()
        ):
            raise ValidationError("PROFILE_SELECTOR_INVALID")
        return {
            str(key): sorted(set(cast(list[str], value))) for key, value in raw.items()
        }
    if (
        set(raw) != {"project_character_id"}
        or not isinstance(raw.get("project_character_id"), int)
        or isinstance(raw.get("project_character_id"), bool)
        or raw["project_character_id"] <= 0
    ):
        raise ValidationError("PROFILE_SELECTOR_INVALID")
    return {"project_character_id": raw["project_character_id"]}


def _finite_number(value: object, *, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("PROFILE_RULE_NUMBER_INVALID")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError("PROFILE_RULE_NUMBER_INVALID")
    return result


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError("ID_INVALID")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
