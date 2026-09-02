from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_style_analysis_migration import open_test_database

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.external_analysis_repository import (
    ExternalAnalysisRepository,
)
from novel_core.style_analysis.resumable_models import PreparedModelCall


def _target(connection: sqlite3.Connection) -> tuple[int, int, int]:
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
        "INSERT INTO style_documents "
        "(kind, project_work_id, project_episode_id) "
        "VALUES ('project_episode_draft', ?, ?)",
        (work_id, episode_id),
    )
    document_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    digest = "a" * 64
    connection.execute(
        "INSERT INTO style_text_revisions "
        "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
        "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
        "normalizer_id, normalizer_version) VALUES "
        "(?, 1, 1, '本文', '本文', ?, ?, ?, 'test', 1)",
        (document_id, digest, digest, digest),
    )
    text_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_structure_revisions "
        "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
        "source_kind, fingerprint) VALUES "
        "(?, 1, 'test', 1, 'automatic', ?)",
        (text_id, digest),
    )
    structure_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    run_id = AnalysisRunRepository(connection).insert_run(
        document_id=document_id,
        analyzer_id="entity-mention-extractor",
        analyzer_version=1,
        text_revision_id=text_id,
        structure_revision_id=structure_id,
        status="running",
        fingerprint=digest,
        config_json="{}",
        started_at="2026-01-01T00:00:00+00:00",
    )
    return document_id, text_id, run_id


def test_external_repository_round_trips_session_task_and_fingerprints(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        document_id, text_id, run_id = _target(connection)
        repository = ExternalAnalysisRepository(connection)
        session_id = repository.insert_session(
            document_id=document_id,
            reference_work_id=None,
            executor_provider="chatgpt_mcp",
            executor_model_id="model-a",
            runtime_contract_fingerprint="a" * 64,
            request_json={"schema_version": 1},
            snapshot_json={"target_kind": "document"},
            cursor_json={"schema_version": 1},
        )
        repository.link_run(session_id, run_id, "created")
        call = PreparedModelCall(
            call_key="call-1",
            analysis_run_id=run_id,
            analyzer_id="entity-mention-extractor",
            analyzer_version=1,
            prompt_id="style.entity_mentions",
            prompt_version=1,
            response_contract_id="style.entity_mentions.v1",
            system_prompt="system",
            user_payload={"blocks": []},
            response_schema={"type": "object"},
        )
        task_id = repository.insert_task(
            session_id=session_id, sequence_no=1, prepared_call=call
        )
        session = repository.get_session(session_id)
        task = repository.get_task(task_id)
        assert session is not None and session.version == 1
        assert task is not None and task.status == "pending"
        assert task.request_fingerprint == repository.request_fingerprint(task_id)
        assert repository.current_pending_task(session_id).id == task_id

        repository.finalize_task(
            task_id=task_id,
            expected_version=1,
            status="accepted",
            response={"mentions": []},
        )
        accepted = repository.get_task(task_id)
        assert accepted is not None
        assert accepted.version == 2
        assert accepted.response_json == '{"mentions":[]}'
        with pytest.raises(ValueError, match="EXTERNAL_SESSION_PENDING_INVALID"):
            repository.assert_session_invariants(session_id)
    finally:
        connection.close()
