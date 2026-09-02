from pathlib import Path

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from test_style_analysis_jobs import _create_reference_analysis

from novel_api.style_analysis.catalog_service import StyleAnalysisCatalogService


def test_semantic_status_prioritizes_stale_over_partial_after_revision_change(
    data_root: Path,
) -> None:
    connection, document_id, text_revision_id, result = _create_reference_analysis(
        data_root
    )
    try:
        assert result.structure_revision_id is not None
        text_row = connection.execute(
            "SELECT document_id, revision_no, source_snapshot_id, project_draft_id, "
            "raw_text, canonical_text, raw_sha256, canonical_sha256, "
            "normalization_input_fingerprint, normalizer_id, normalizer_version "
            "FROM style_text_revisions WHERE id = ?",
            (text_revision_id,),
        ).fetchone()
        assert text_row is not None
        connection.execute(
            "INSERT INTO style_text_revisions "
            "(document_id, revision_no, source_snapshot_id, project_draft_id, "
            "raw_text, canonical_text, raw_sha256, canonical_sha256, "
            "normalization_input_fingerprint, normalizer_id, normalizer_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                text_row[0],
                text_row[1] + 1,
                text_row[2],
                text_row[3],
                text_row[4],
                text_row[5],
                text_row[6],
                text_row[7],
                "d" * 64,
                text_row[9],
                text_row[10],
            ),
        )
        new_text_revision_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        connection.execute(
            "INSERT INTO style_structure_revisions "
            "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
            "source_kind, fingerprint) VALUES (?, 1, 'test', 1, 'automatic', ?)",
            (new_text_revision_id, "b" * 64),
        )
        new_structure_revision_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        connection.execute(
            "UPDATE style_documents SET current_text_revision_id = ?, "
            "current_structure_revision_id = ? WHERE id = ?",
            (new_text_revision_id, new_structure_revision_id, document_id),
        )
        entity_row = connection.execute(
            "SELECT analyzer_version, config_json, state_fingerprint, "
            "policy_input_fingerprint, prompt_id, prompt_version "
            "FROM style_analysis_runs WHERE document_id = ? "
            "AND analyzer_id = 'entity-mention-extractor' ORDER BY id LIMIT 1",
            (document_id,),
        ).fetchone()
        assert entity_row is not None
        repository = AnalysisRunRepository(connection)
        repository.insert_run(
            document_id=document_id,
            analyzer_id="entity-mention-extractor",
            analyzer_version=entity_row[0],
            text_revision_id=new_text_revision_id,
            structure_revision_id=new_structure_revision_id,
            status="partial",
            fingerprint="c" * 64,
            config_json=entity_row[1],
            state_fingerprint=entity_row[2],
            policy_input_fingerprint=entity_row[3],
            prompt_id=entity_row[4],
            prompt_version=entity_row[5],
            started_at="2026-09-02T00:00:00Z",
        )
        repository.commit()

        status = StyleAnalysisCatalogService(connection).analysis_status(
            document_id, new_text_revision_id, new_structure_revision_id
        )

        assert status["semantic"] == {
            "state": "stale",
            "reasons": ["CURRENT_REVISION_CHANGED"],
        }
    finally:
        connection.close()
