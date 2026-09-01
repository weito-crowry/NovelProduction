from __future__ import annotations

import sqlite3


def latest_override(
    connection: sqlite3.Connection,
    subject_type: str,
    subject_id: int,
    field_path: str,
) -> tuple[int, str, object] | None:
    rows = connection.execute(
        "SELECT id, operation, value_json FROM style_manual_overrides "
        "WHERE subject_type = ? AND subject_id = ? AND field_path = ? "
        "ORDER BY created_at, id",
        (subject_type, subject_id, field_path),
    ).fetchall()
    active: list[tuple[int, str, object]] = []
    for row in rows:
        operation = str(row[1])
        if operation in {"set", "clear"}:
            active.append((int(row[0]), operation, row[2]))
        elif active:
            active.pop()
    return active[-1] if active else None
