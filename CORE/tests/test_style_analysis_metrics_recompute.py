from __future__ import annotations

from pathlib import Path

import pytest
from test_style_analysis_semantic_metrics import _fixture

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator


def test_internal_metrics_preset_recomputes_semantic_metrics_without_full_analysis(
    tmp_path: Path,
) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        result = DocumentAnalysisOrchestrator(
            connection, model_client=None
        ).analyze_document(
            document_id=document_id,
            text_revision_id=1,
            structure_revision_id=1,
            preset="metrics",
        )
        assert result.status in {"succeeded", "partial"}
        assert result.run_ids
        assert connection.execute(
            "SELECT analyzer_id FROM style_analysis_runs WHERE id=?",
            (result.run_ids[-1],),
        ).fetchone() == ("style-metrics-semantic",)
        assert not any(
            connection.execute(
                "SELECT analyzer_id FROM style_analysis_runs WHERE id=?", (run_id,)
            ).fetchone()[0]
            in {"entity-resolver", "speaker-attribution"}
            for run_id in result.run_ids
        )
    finally:
        connection.close()


def test_internal_metrics_preset_requires_explicit_structure_revision(
    tmp_path: Path,
) -> None:
    connection, document_id, _, _ = _fixture(tmp_path)
    try:
        with pytest.raises(ValueError, match="STRUCTURE_REVISION_REQUIRED"):
            DocumentAnalysisOrchestrator(
                connection, model_client=None
            ).analyze_document(
                document_id=document_id,
                text_revision_id=1,
                preset="metrics",
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM style_analysis_runs"
        ).fetchone() == (3,)
    finally:
        connection.close()
