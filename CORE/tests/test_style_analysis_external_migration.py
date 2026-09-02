from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_style_analysis_migration import open_test_database


def test_external_migration_is_applied_and_has_exact_tables(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        versions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        assert versions[-1] == "009_style_analysis_external_agent.sql"
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "style_external_analysis_sessions",
            "style_external_analysis_tasks",
            "style_external_analysis_session_runs",
        } <= tables
    finally:
        connection.close()


def test_external_session_checks_target_and_status(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO style_external_analysis_sessions "
                "(executor_provider, executor_model_id, runtime_contract_fingerprint, "
                "status, request_json, snapshot_json, cursor_json) "
                "VALUES ('chatgpt_mcp', 'model', ?, 'active', '{}', '{}', '{}')",
                ("a" * 64,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO style_external_analysis_sessions "
                "(document_id, executor_provider, executor_model_id, "
                "runtime_contract_fingerprint, status, request_json, snapshot_json, "
                "cursor_json) VALUES (1, 'other', 'model', ?, 'active', "
                "'{}', '{}', '{}')",
                ("a" * 64,),
            )
    finally:
        connection.close()


def test_external_task_pending_index_and_attempt_checks_exist(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list('style_external_analysis_tasks')"
            )
        }
        assert "idx_external_tasks_one_pending" in indexes
        assert {
            row[2]
            for row in connection.execute(
                "PRAGMA index_info('idx_external_tasks_one_pending')"
            )
        } == {"session_id"}
    finally:
        connection.close()
