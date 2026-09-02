from __future__ import annotations

import sqlite3


def current_mention_ids(
    connection: sqlite3.Connection,
    entity_run_id: int,
    structure_revision_id: int,
) -> frozenset[int]:
    rows = connection.execute(
        "SELECT DISTINCT m.id FROM style_mentions m "
        "JOIN style_analysis_run_dependencies links "
        "ON links.dependency_run_id = m.analysis_run_id "
        "JOIN style_analysis_runs dep ON dep.id = m.analysis_run_id "
        "WHERE links.run_id = ? AND dep.analyzer_id = 'entity-mention-extractor' "
        "AND m.structure_revision_id = ? ORDER BY m.id",
        (entity_run_id, structure_revision_id),
    ).fetchall()
    return frozenset(int(row[0]) for row in rows)
