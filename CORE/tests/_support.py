from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from novel_core.repositories.work_repository import WorkRepository


def initialize_test_work(connection: sqlite3.Connection, working_title: str) -> None:
    repository = WorkRepository(connection)
    try:
        repository.begin_write()
        repository.create(
            slug="main",
            working_title=working_title,
            genre="",
            premise="",
            themes_json="{}",
            description="",
            production_status="planned",
        )
        repository.commit()
    except Exception:
        repository.rollback()
        raise


def json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_values = asdict(value)
        return {key: json_value(item) for key, item in dataclass_values.items()}
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [json_value(item) for item in value]
    return value
