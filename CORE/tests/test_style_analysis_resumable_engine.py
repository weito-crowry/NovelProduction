from __future__ import annotations

import sqlite3
from pathlib import Path

from test_style_analysis_migration import open_test_database

from novel_core.style_analysis.resumable_engine import ResumableDocumentAnalysisEngine
from novel_core.style_analysis.resumable_models import DocumentAnalysisRequest
from novel_core.style_analysis.runtime_models import AnalysisPolicy


def _document(connection: sqlite3.Connection) -> tuple[int, int]:
    connection.execute("INSERT INTO works (slug, working_title) VALUES ('w', 'W')")
    work_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'C')",
        (work_id,),
    )
    chapter_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO episodes "
        "(work_id, chapter_id, position, title) VALUES (?, ?, 1, 'E')",
        (work_id, chapter_id),
    )
    episode_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_documents (kind, project_work_id, project_episode_id) "
        "VALUES ('project_episode_draft', ?, ?)",
        (work_id, episode_id),
    )
    document_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    digest = "a" * 64
    text = "本文\n\n続き"
    connection.execute(
        "INSERT INTO style_text_revisions "
        "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
        "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
        "normalizer_id, normalizer_version) "
        "VALUES (?, 1, 1, ?, ?, ?, ?, ?, 'test', 1)",
        (document_id, text, text, digest, digest, digest),
    )
    text_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_structure_revisions "
        "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
        "source_kind, fingerprint) VALUES (?, 1, 'test', 1, 'automatic', ?)",
        (text_id, digest),
    )
    structure_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_scenes "
        "(structure_revision_id, order_index, start_cp, end_cp) VALUES (?, 1, 0, 2)",
        (structure_id,),
    )
    scene_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_blocks "
        "(structure_revision_id, scene_id, order_index, paragraph_index, block_type, "
        "start_cp, end_cp) VALUES (?, ?, 1, 1, 'narration', 0, 2)",
        (structure_id, scene_id),
    )
    return document_id, text_id


def test_full_advance_prepares_one_call_without_provider_or_commit(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        document_id, text_id = _document(connection)
        connection.commit()
        commits: list[bool] = []
        connection.set_trace_callback(
            lambda statement: commits.append(statement.upper() == "COMMIT")
        )
        connection.execute("BEGIN IMMEDIATE")
        result = ResumableDocumentAnalysisEngine(
            connection,
            model_provider="chatgpt_mcp",
            model_id="gpt-test",
            policy=AnalysisPolicy(),
            checkpoint=lambda: None,
        ).advance(
            DocumentAnalysisRequest(document_id, text_id),
            {"schema_version": 1},
        )

        assert result.pending_call is not None
        assert result.result is None
        assert result.pending_call.analysis_run_id > 0
        assert result.pending_call.prompt_id == "style.scene_boundary"
        assert result.pending_call.response_contract_id == "style.scene_boundary.v1"
        assert result.cursor["stage"] == "scene_boundary"
        assert not any(commits)
    finally:
        connection.close()
