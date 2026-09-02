from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol, TypeAlias, cast

JsonObject: TypeAlias = dict[str, object]  # noqa: UP040


@dataclass(frozen=True, slots=True)
class ModelRequest:
    prompt_id: str
    prompt_version: int
    system_prompt: str
    user_payload: JsonObject


class ModelClient(Protocol):
    def complete_json(self, request: ModelRequest) -> JsonObject: ...


def complete_validated_json(
    client: ModelClient,
    request: ModelRequest,
    validator: Callable[[JsonObject], JsonObject],
) -> JsonObject:
    """Complete one response and validate its analyzer-level JSON contract.

    API clients may implement ``complete_json_validated`` to include the
    contract error in their single repair attempt.  The fallback keeps CORE
    analyzers compatible with small test fakes and other existing clients.
    """
    validated = getattr(client, "complete_json_validated", None)
    if callable(validated):
        return cast(JsonObject, validated(request, validator))
    return validator(client.complete_json(request))


def validate_model_object(
    value: object,
    *,
    required: Iterable[str] = (),
    allowed: Iterable[str] | None = None,
) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("MODEL_TOP_LEVEL_OBJECT_REQUIRED")
    allowed_keys = set(allowed) if allowed is not None else set(required)
    unknown = sorted(set(value) - allowed_keys)
    if unknown:
        raise ValueError(f"UNKNOWN_KEY:{unknown[0]}")
    missing = sorted(set(required) - set(value))
    if missing:
        raise ValueError(f"REQUIRED_KEY_MISSING:{missing[0]}")
    return dict(value)


def validate_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("CONFIDENCE_INVALID")
    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("CONFIDENCE_INVALID")
    return confidence


def validate_positive_id(value: object, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("ID_INVALID")
    return value


def require_int(value: object, *, code: str = "MODEL_ITEM_INVALID") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(code)
    return value


def validate_span(
    block_text: str, start: object, end: object, surface: object
) -> tuple[int, int]:
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or start >= end
        or end > len(block_text)
    ):
        raise ValueError("SPAN_INVALID")
    if not isinstance(surface, str):
        raise ValueError("SPAN_SURFACE_MISMATCH")
    if block_text[start:end] == surface:
        return start, end
    occurrences: list[tuple[int, int]] = []
    cursor = block_text.find(surface)
    while cursor >= 0:
        occurrences.append((cursor, cursor + len(surface)))
        cursor = block_text.find(surface, cursor + 1)
    if len(occurrences) == 1:
        return occurrences[0]
    raise ValueError("SPAN_SURFACE_MISMATCH")


def validate_enum(value: object, allowed: Iterable[str], *, code: str = "ENUM") -> str:
    if not isinstance(value, str) or value not in set(allowed):
        raise ValueError(f"{code}_INVALID")
    return value


def validate_block_item(
    item: object,
    *,
    block_texts: Mapping[int, str],
    required: tuple[str, ...],
    allowed: tuple[str, ...],
) -> JsonObject:
    obj = validate_model_object(item, required=required, allowed=allowed)
    block_id = validate_positive_id(obj.get("block_id"))
    assert block_id is not None
    text = block_texts.get(block_id)
    if text is None:
        raise ValueError("MODEL_ITEM_ID_INVALID")
    normalized_start, normalized_end = validate_span(
        text,
        obj.get("start_in_block"),
        obj.get("end_in_block"),
        obj.get("surface"),
    )
    obj["start_in_block"] = normalized_start
    obj["end_in_block"] = normalized_end
    return obj
