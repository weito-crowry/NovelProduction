from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from pydantic import BaseModel


def serialize_value(value: Any) -> Any:
    if isinstance(value, BaseException | sqlite3.Connection):
        raise TypeError("value is not JSON serializable")
    if isinstance(value, BaseModel):
        return serialize_value(value.model_dump())
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: serialize_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [serialize_value(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError("value is not JSON serializable")
