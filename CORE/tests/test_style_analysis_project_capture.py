from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_style_analysis_migration import open_test_database

from novel_core.document import (
    BlockAttrs,
    NovelBlock,
    NovelDocument,
    render_plain_text_projection,
    serialize_document_json,
)
from novel_core.errors import AnalysisCancelledError
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.lint_repository import LintRepository
from novel_core.style_analysis.lint_service import StyleLintService
from novel_core.style_analysis.profile_service import ProfileService
from novel_core.style_analysis.structure_models import SceneRecord
from novel_core.style_analysis.text_service import StyleTextService


def block(block_id: str, block_type: str, html: str) -> NovelBlock:
    return NovelBlock(
        id=f"blk_{block_id * 32}"[:36],
        type=block_type,  # type: ignore[arg-type]
        html=html,
        attrs=BlockAttrs(),
    )


def test_plain_text_projection_uses_base_text_and_records_separator_offsets() -> None:
    result = render_plain_text_projection(
        NovelDocument(
            blocks=(
                block("a", "narration", "A<br>B"),
                block("b", "separator", ""),
                block("c", "dialogue", "<ruby>東京<rt>とうきょう</rt></ruby>C"),
                block("d", "note", "制作メモ"),
            )
        )
    )

    assert result.raw_text == "A\nB\n\n東京C"
    assert result.scene_break_offsets_raw == (3,)


def test_plain_text_projection_preserves_empty_paragraphs_and_ignores_notes() -> None:
    result = render_plain_text_projection(
        NovelDocument(
            blocks=(
                block("a", "narration", "A"),
                block("b", "narration", ""),
                block("c", "note", "note"),
                block("d", "narration", "C"),
            )
        )
    )

    assert result.raw_text == "A\n\n\n\nC"
    assert result.scene_break_offsets_raw == ()


def test_project_draft_revision_uses_formal_normalizer_and_reuses_same_input(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        connection.execute("INSERT INTO works (slug, working_title) VALUES ('w', 'W')")
        work_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'C')",
            (work_id,),
        )
        chapter_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO episodes (work_id, chapter_id, position, title) "
            "VALUES (?, ?, 1, 'E')",
            (work_id, chapter_id),
        )
        episode_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        document = NovelDocument(blocks=(block("a", "narration", "本文"),))
        connection.execute(
            "INSERT INTO drafts (work_id, episode_id, revision, document_json) "
            "VALUES (?, ?, 1, ?)",
            (work_id, episode_id, serialize_document_json(document)),
        )
        draft_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO style_documents (kind, project_work_id, project_episode_id) "
            "VALUES ('project_episode_draft', ?, ?)",
            (work_id, episode_id),
        )
        document_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )

        service = StyleTextService(connection)
        first = service.insert_project_draft_revision(
            document_id=document_id,
            project_draft_id=draft_id,
            raw_text="本文\r\n\r\n続き",
            structure_hints_raw=[2],
        )
        second = service.insert_project_draft_revision(
            document_id=document_id,
            project_draft_id=draft_id,
            raw_text="本文\r\n\r\n続き",
            structure_hints_raw=[2],
        )
        connection.commit()

        assert first.id == second.id
        assert first.project_draft_id == draft_id
        assert first.source_snapshot_id is None
        assert first.canonical_text == "本文\n\n続き"
        assert json.loads(first.metadata_json)["normalization_warnings"] == []
    finally:
        connection.close()


def test_lint_evaluates_document_range_and_persists_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        connection.execute("INSERT INTO works (slug, working_title) VALUES ('w', 'W')")
        work_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'C')",
            (work_id,),
        )
        chapter_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO episodes (work_id, chapter_id, position, title) "
            "VALUES (?, ?, 1, 'E')",
            (work_id, chapter_id),
        )
        episode_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO style_documents (kind, project_work_id, project_episode_id) "
            "VALUES ('project_episode_draft', ?, ?)",
            (work_id, episode_id),
        )
        document_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        digest = "a" * 64
        connection.execute(
            "INSERT INTO style_text_revisions "
            "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
            "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
            "normalizer_id, normalizer_version) "
            "VALUES (?, 1, 1, 'A', 'A', ?, ?, ?, 'test', 1)",
            (document_id, digest, digest, digest),
        )
        text_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            "INSERT INTO style_structure_revisions "
            "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
            "source_kind, fingerprint) VALUES (?, 1, 'test', 1, 'automatic', ?)",
            (text_id, digest),
        )
        structure_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        connection.execute(
            "UPDATE style_documents SET current_text_revision_id = ?, "
            "current_structure_revision_id = ? WHERE id = ?",
            (text_id, structure_id, document_id),
        )
        run_id = AnalysisRunRepository(connection).insert_run(
            document_id=document_id,
            analyzer_id="style-metrics-basic",
            analyzer_version=1,
            text_revision_id=text_id,
            structure_revision_id=structure_id,
            status="succeeded",
            fingerprint=digest,
            config_json='{"metric_versions":{}}',
            started_at="2026-01-01 00:00:00",
        )
        connection.execute(
            "INSERT INTO style_measurements "
            "(analysis_run_id, structure_revision_id, target_type, target_id, "
            "metric_name, metric_version, value_int, sample_count) "
            "VALUES (?, ?, 'document', ?, 'text.char_count', 1, 1, 1)",
            (run_id, structure_id, document_id),
        )
        connection.execute(
            "INSERT INTO style_blocks "
            "(structure_revision_id, scene_id, order_index, paragraph_index, "
            "block_type, start_cp, end_cp) VALUES (?, NULL, 1, 1, 'narration', 0, 1)",
            (structure_id,),
        )
        connection.execute(
            "INSERT INTO style_measurements "
            "(analysis_run_id, structure_revision_id, target_type, target_id, "
            "metric_name, metric_version, value_real, sample_count) "
            "VALUES (?, ?, 'document', ?, 'sentence.len.p50', 1, 50, 1)",
            (run_id, structure_id, document_id),
        )
        connection.execute(
            "INSERT INTO style_measurements "
            "(analysis_run_id, structure_revision_id, target_type, target_id, "
            "metric_name, metric_version, value_real, sample_count) "
            "VALUES (?, ?, 'document', ?, 'narration.run_len.p50', 1, 40, 1)",
            (run_id, structure_id, document_id),
        )
        profile = ProfileService(connection).create_manual(
            name="P",
            rules=(
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "text.char_count",
                    "metric_version": 1,
                    "preferred_value": 15,
                    "min_value": 10,
                    "max_value": 20,
                    "weight": 1.0,
                    "enabled": True,
                    "severity_policy": "standard",
                },
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "sentence.len.p50",
                    "metric_version": 1,
                    "preferred_value": 15,
                    "min_value": 10,
                    "max_value": 20,
                    "weight": 1.0,
                    "enabled": True,
                    "severity_policy": "standard",
                },
                {
                    "target_scope": "document",
                    "scope_selector": {},
                    "metric_name": "narration.run_len.p50",
                    "metric_version": 1,
                    "preferred_value": 15,
                    "min_value": 10,
                    "max_value": 20,
                    "weight": 1.0,
                    "enabled": True,
                    "severity_policy": "standard",
                },
            ),
        )
        monkeypatch.setattr(
            CurrentRunResolver,
            "resolve",
            lambda self, *args: (
                SimpleNamespace(id=run_id)
                if args[-1] == "style-metrics-basic"
                else None
            ),
        )
        events: list[tuple[int, int]] = []
        service = StyleLintService(connection)
        result = service.run(
            document_id=document_id,
            text_revision_id=text_id,
            structure_revision_id=structure_id,
            profile_id=profile.profile.id,
            profile_version_no=profile.version.version_no,
            progress_callback=lambda current, total: events.append((current, total)),
        )
        connection.commit()

        assert result.run.status == "succeeded"
        assert result.run.enabled_rule_count == 3
        assert result.run.applicable_rule_count == 3
        assert result.run.missing_rule_count == 0
        assert {
            finding.metric_name: finding.observed_value for finding in result.findings
        } == {
            "text.char_count": 1.0,
            "sentence.len.p50": 50.0,
            "narration.run_len.p50": 40.0,
        }
        assert events[0] == (0, 3)
        assert events[-1] == (3, 3)
        with pytest.raises(AnalysisCancelledError):
            service.run(
                document_id=document_id,
                text_revision_id=text_id,
                structure_revision_id=structure_id,
                profile_id=profile.profile.id,
                profile_version_no=profile.version.version_no,
                cancellation_probe=lambda: True,
            )
        narration_finding = next(
            finding
            for finding in result.findings
            if finding.metric_name == "narration.run_len.p50"
        )
        assert (
            json.loads(narration_finding.evidence_json)["evidence_kind"]
            == "narration_run"
        )

        reviewed = service.review_finding(
            next(
                finding
                for finding in result.findings
                if finding.metric_name == "text.char_count"
            ).id,
            "acknowledged",
            "確認済み",
        )
        connection.commit()
        assert reviewed.review_status == "acknowledged"

        repeated = service.run(
            document_id=document_id,
            text_revision_id=text_id,
            structure_revision_id=structure_id,
            profile_id=profile.profile.id,
            profile_version_no=profile.version.version_no,
        )
        connection.commit()
        repeated_text = next(
            finding
            for finding in repeated.findings
            if finding.metric_name == "text.char_count"
        )
        assert repeated_text.review_status == "acknowledged"

        third = service.run(
            document_id=document_id,
            text_revision_id=text_id,
            structure_revision_id=structure_id,
            profile_id=profile.profile.id,
            profile_version_no=profile.version.version_no,
        )
        connection.commit()
        third_text = next(
            finding
            for finding in third.findings
            if finding.metric_name == "text.char_count"
        )
        assert third_text.review_status is None

        original_insert = LintRepository.insert_finding

        def fail_insert(self, values):
            raise RuntimeError("forced finding persistence failure")

        monkeypatch.setattr(LintRepository, "insert_finding", fail_insert)
        with pytest.raises(RuntimeError, match="forced finding persistence failure"):
            service.run(
                document_id=document_id,
                text_revision_id=text_id,
                structure_revision_id=structure_id,
                profile_id=profile.profile.id,
                profile_version_no=profile.version.version_no,
            )
        connection.commit()
        latest = connection.execute(
            "SELECT status FROM style_lint_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert latest == ("failed",)
        failed_run_id = int(
            connection.execute(
                "SELECT id FROM style_lint_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM style_findings WHERE lint_run_id = ?",
            (failed_run_id,),
        ).fetchone() == (0,)
        monkeypatch.setattr(LintRepository, "insert_finding", original_insert)
    finally:
        connection.close()


def test_lint_progress_separates_selector_missing_from_evaluated_pairs(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        unavailable_scene_rule = SimpleNamespace(
            id=1,
            target_scope="scene",
            scope_selector_json='{"function":["exposition"]}',
            metric_name="text.char_count",
            metric_version=1,
            min_value=10,
            max_value=20,
            preferred_value=15,
            weight=1.0,
        )
        available_document_rule = SimpleNamespace(
            id=2,
            target_scope="document",
            scope_selector_json="{}",
            metric_name="text.char_count",
            metric_version=1,
            min_value=10,
            max_value=20,
            preferred_value=15,
            weight=1.0,
        )
        events: list[tuple[int, int]] = []
        result = StyleLintService(connection)._candidates(
            1,
            (unavailable_scene_rule, available_document_rule),
            (SceneRecord(1, 1, 1, 0, 1),),
            None,
            [],
            [],
            {("basic", "document", 1, "text.char_count", 1): 15.0},
            {},
            1,
            1,
            lambda current, total: events.append((current, total)),
            None,
        )

        assert result[1:3] == (2, 1)
        assert events == [(0, 2), (1, 2), (2, 2)]
    finally:
        connection.close()
