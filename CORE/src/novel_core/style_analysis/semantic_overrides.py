from __future__ import annotations

import sqlite3


def latest_override(
    connection: sqlite3.Connection,
    subject_type: str,
    subject_id: int,
    field_path: str,
) -> tuple[int, str, object] | None:
    row = connection.execute(
        "SELECT id, operation, value_json FROM style_manual_overrides "
        "WHERE subject_type = ? AND subject_id = ? AND field_path = ? "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (subject_type, subject_id, field_path),
    ).fetchone()
    if row is None or row[1] == "revert":
        return None
    return int(row[0]), str(row[1]), row[2]
