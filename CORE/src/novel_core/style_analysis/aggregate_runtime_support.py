from __future__ import annotations

import sqlite3
from typing import cast

from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json


def semantic_metric_state(
    connection: sqlite3.Connection,
    document_id: int,
    structure_id: int,
    term_run_id: int,
    term_status: str,
) -> str:
    field_paths = (
        "block.speaker",
        "block.semantic_primary",
        "term.novelty",
        "term_mention.explanation",
    )
    placeholders = ", ".join("?" for _ in field_paths)
    overrides = connection.execute(
        "SELECT subject_type, subject_id, field_path, operation, value_json, "
        "structure_revision_id FROM style_manual_overrides "
        "WHERE document_id = ? AND field_path IN (" + placeholders + ") "
        "AND (structure_revision_id IS NULL OR structure_revision_id = ?) "
        "ORDER BY subject_type, subject_id, field_path, created_at, id",
        (document_id, *field_paths, structure_id),
    ).fetchall()
    reviews = connection.execute(
        "SELECT subject_type, subject_id, field_path, review_status, "
        "analysis_run_id FROM style_inference_reviews "
        "WHERE document_id = ? AND field_path IN (" + placeholders + ") "
        "ORDER BY subject_type, subject_id, field_path, created_at, id",
        (document_id, *field_paths),
    ).fetchall()
    state: list[dict[str, object]] = [
        {
            "kind": "override",
            "subject_type": str(row[0]),
            "subject_id": int(row[1]),
            "field_path": str(row[2]),
            "operation": str(row[3]),
            "value_json": row[4],
            "structure_revision_id": row[5],
        }
        for row in overrides
    ] + [
        {
            "kind": "review",
            "subject_type": str(row[0]),
            "subject_id": int(row[1]),
            "field_path": str(row[2]),
            "review_status": str(row[3]),
            "analysis_run_id": int(row[4]),
        }
        for row in reviews
    ]
    return fingerprint_json(
        cast(
            JsonValue,
            {
                "metric_effective_state": state,
                "term_first_appearance": {
                    "document_id": document_id,
                    "text_revision_id": text_revision_for_structure(
                        connection, structure_id
                    ),
                    "structure_revision_id": structure_id,
                    "term_resolver_run_id": term_run_id,
                    "resolver_status": term_status,
                },
            },
        )
    )


def text_revision_for_structure(
    connection: sqlite3.Connection, structure_id: int
) -> int | None:
    row = connection.execute(
        "SELECT text_revision_id FROM style_structure_revisions WHERE id = ?",
        (structure_id,),
    ).fetchone()
    return None if row is None else int(row[0])
