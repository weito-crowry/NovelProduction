from __future__ import annotations

import hashlib
import json
from typing import TypeAlias

JsonPrimitive: TypeAlias = None | bool | int | float | str  # noqa: UP040
JsonValue: TypeAlias = (  # noqa: UP040
    JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]  # noqa: UP040


def canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def fingerprint_json(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
