from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from test_style_analysis_migration import open_test_database

from novel_core.errors import AnalysisCancelledError
from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.model_contracts import (
    ModelRequest,
    validate_model_object,
    validate_span,
)
from novel_core.style_analysis.model_prompts import PROMPT_REGISTRY
from novel_core.style_analysis.resolver_candidates import build_context_window
from novel_core.style_analysis.term_service import TermService


def test_semantics_migration_creates_all_sa_d_tables(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        tables = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'style_%' ORDER BY rowid"
            )
        )
        assert tables[-11:] == (
            "style_entities",
            "style_mentions",
            "style_entity_aliases",
            "style_entity_character_links",
            "style_terms",
            "style_term_aliases",
            "style_term_mentions",
            "style_annotations",
            "style_review_items",
            "style_inference_reviews",
            "style_manual_overrides",
        )
        assert "entity_id" not in {
            row[1] for row in connection.execute("PRAGMA table_info(style_mentions)")
        }
    finally:
        connection.close()


def test_semantics_scope_and_annotation_span_constraints(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO style_entities "
                "(reference_work_id, document_id, entity_type, canonical_name, origin) "
                "VALUES (1, 2, 'person', 'x', 'inferred')"
            )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(style_annotations)")
        }
        assert {"start_cp", "end_cp", "analysis_run_id"} <= columns
    finally:
        connection.close()


def test_prompt_registry_is_exactly_the_sa_d_ten() -> None:
    assert tuple(PROMPT_REGISTRY) == (
        "style.scene_boundary",
        "style.entity_mentions",
        "style.entity_resolution",
        "style.speaker_attribution",
        "style.term_candidates",
        "style.term_resolution",
        "style.term_explanation",
        "style.scene_semantics",
        "style.block_semantic",
        "style.pov",
    )
    assert all(version == 1 for version in PROMPT_REGISTRY.values())


def test_model_validation_rejects_unknown_keys_and_invalid_spans() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_KEY"):
        validate_model_object({"ok": 1, "extra": 2}, required=("ok",))
    with pytest.raises(ValueError, match="SPAN_INVALID"):
        validate_span("本文", 1, 1, "")
    with pytest.raises(ValueError, match="SPAN_SURFACE_MISMATCH"):
        validate_span("本文", 0, 1, "別")


def test_context_window_is_scene_bounded_and_subject_is_once() -> None:
    blocks = [
        {"block_id": 1, "scene_id": 1, "block_type": "narration", "text": "a"},
        {"block_id": 2, "scene_id": 1, "block_type": "dialogue", "text": "b"},
        {"block_id": 3, "scene_id": 2, "block_type": "narration", "text": "c"},
        {"block_id": 4, "scene_id": 1, "block_type": "narration", "text": "d"},
    ]
    previous, subject, following = build_context_window(
        blocks, subject_block_id=2, before=2, after=2
    )
    assert [block["block_id"] for block in previous] == [1]
    assert subject["block_id"] == 2
    assert [block["block_id"] for block in following] == [4]


def test_registry_exact_match_requires_literal_canonical_or_alias_text(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        connection.execute("INSERT INTO works (slug, working_title) VALUES ('x', 'X')")
        work_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'c')",
            (work_id,),
        )
        chapter_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO episodes (work_id, chapter_id, position, title) "
            "VALUES (?, ?, 1, 'e')",
            (work_id, chapter_id),
        )
        episode_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO style_documents "
            "(kind, project_work_id, project_episode_id) VALUES "
            "('project_episode_draft', ?, ?)",
            (work_id, episode_id),
        )
        document_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO style_entities "
            "(document_id, entity_type, canonical_name, origin) "
            "VALUES (?, 'person', '田 中', 'manual')",
            (document_id,),
        )
        connection.execute(
            "INSERT INTO style_terms "
            "(document_id, canonical_label, term_type, origin) "
            "VALUES (?, '魔法 書', 'object', 'manual')",
            (document_id,),
        )
        connection.commit()

        assert (
            EntityService(connection).exact_matches(
                document_id=document_id, surface="田中"
            )
            == ()
        )
        assert (
            TermService(connection).exact_matches(
                document_id=document_id, surface="魔法書"
            )
            == ()
        )

        orchestrator = DocumentAnalysisOrchestrator(
            connection, model_client=None, model_provider=None, model_id=None
        )
        entity_state = orchestrator._entity_registry_state(document_id)
        term_state = orchestrator._term_registry_state(document_id)
        connection.execute(
            "INSERT INTO style_entities "
            "(document_id, entity_type, canonical_name, origin) "
            "VALUES (?, 'person', '推論人物', 'inferred')",
            (document_id,),
        )
        inferred_entity_id = connection.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO style_entity_aliases "
            "(entity_id, alias, alias_kind, origin) "
            "VALUES (?, '推論別名', 'name', 'inferred')",
            (inferred_entity_id,),
        )
        connection.execute(
            "INSERT INTO style_terms "
            "(document_id, canonical_label, term_type, origin) "
            "VALUES (?, '推論用語', 'object', 'inferred')",
            (document_id,),
        )
        inferred_term_id = connection.execute("SELECT last_insert_rowid()").fetchone()[
            0
        ]
        connection.execute(
            "INSERT INTO style_term_aliases "
            "(term_id, alias, origin) VALUES (?, '推論別名', 'inferred')",
            (inferred_term_id,),
        )
        connection.commit()
        assert orchestrator._entity_registry_state(document_id) == entity_state
        assert orchestrator._term_registry_state(document_id) == term_state

        connection.execute(
            "INSERT INTO style_manual_overrides "
            "(document_id, subject_type, subject_id, field_path, operation, "
            "value_json) "
            "VALUES (?, 'entity', 1, 'entity.enabled', 'set', 'false')",
            (document_id,),
        )
        connection.commit()
        assert orchestrator._entity_registry_state(document_id) != entity_state
    finally:
        connection.close()


def test_pronoun_has_no_inferred_alias_kind() -> None:
    from novel_core.style_analysis.analysis_orchestrator import _alias_kind

    assert _alias_kind("proper_name") == "name"
    assert _alias_kind("alias") == "nickname"
    assert _alias_kind("role_title") == "role"
    assert _alias_kind("pronoun") == "pronoun"


def test_term_novelty_reduction_ignores_uncertain_when_one_concrete_value_remains() -> (
    None
):
    from novel_core.style_analysis.analysis_orchestrator import reduce_term_novelty

    assert reduce_term_novelty(("work_specific", "uncertain")) == "work_specific"
    assert reduce_term_novelty(("work_specific", "other")) == "uncertain"
    assert reduce_term_novelty(("uncertain", "uncertain")) == "uncertain"


def test_orchestrator_cancellation_probe_is_a_safe_point(tmp_path: Path) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        orchestrator = DocumentAnalysisOrchestrator(
            connection,
            model_client=None,
            cancellation_probe=lambda: True,
        )
        with pytest.raises(AnalysisCancelledError):
            orchestrator._safe_point()
    finally:
        connection.close()


class _FakeModel:
    def __init__(self, *, boundary: bool = False) -> None:
        self.boundary = boundary

    def complete_json(self, request: ModelRequest) -> dict[str, object]:
        if request.prompt_id == "style.entity_mentions":
            return {"mentions": []}
        if request.prompt_id == "style.term_candidates":
            return {"terms": []}
        if request.prompt_id == "style.speaker_attribution":
            return {
                "speaker_entity_id": None,
                "confidence": 0.0,
                "evidence_block_ids": [],
                "reason_code": "unknown",
            }
        if request.prompt_id == "style.pov":
            return {"pov_mode": "unclear", "pov_entity_id": None, "confidence": 0.1}
        if request.prompt_id == "style.scene_boundary":
            if self.boundary:
                blocks = request.user_payload.get("blocks")
                if isinstance(blocks, list) and len(blocks) >= 2:
                    first = blocks[0]
                    if isinstance(first, dict) and isinstance(
                        first.get("block_id"), int
                    ):
                        return {
                            "boundaries": [
                                {
                                    "after_block_id": first["block_id"],
                                    "reasons": ["time_shift"],
                                    "confidence": 0.95,
                                }
                            ]
                        }
            return {"boundaries": []}
        if request.prompt_id == "style.scene_semantics":
            return {
                "function": [{"label": "daily", "confidence": 0.9}],
                "tone": [{"label": "calm", "confidence": 0.9}],
                "pace": {"label": "medium", "confidence": 0.9},
                "information_load": {"label": "low", "confidence": 0.9},
                "interaction": {"label": "dialogue", "confidence": 0.9},
            }
        if request.prompt_id == "style.block_semantic":
            return {"label": "description", "confidence": 0.9}
        raise AssertionError(request.prompt_id)


def test_document_orchestrator_persists_sa_d_runs_and_annotations(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        connection.execute("INSERT INTO works (slug, working_title) VALUES ('x', 'X')")
        work_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'c')",
            (work_id,),
        )
        chapter_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO episodes (work_id, chapter_id, position, title) "
            "VALUES (?, ?, 1, 'e')",
            (work_id, chapter_id),
        )
        episode_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO style_documents "
            "(kind, project_work_id, project_episode_id) "
            "VALUES ('project_episode_draft', ?, ?)",
            (work_id, episode_id),
        )
        document_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        digest = "b" * 64
        connection.execute(
            "INSERT INTO style_text_revisions "
            "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
            "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
            "normalizer_id, normalizer_version) "
            "VALUES (?, 1, 1, ?, ?, ?, ?, ?, 'test', 1)",
            (
                document_id,
                "朝。\n「行こう」",
                "朝。\n「行こう」",
                digest,
                digest,
                digest,
            ),
        )
        text_revision_id = connection.execute("SELECT last_insert_rowid()").fetchone()[
            0
        ]
        connection.execute(
            "INSERT INTO style_structure_revisions "
            "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
            "source_kind, fingerprint) "
            "VALUES (?, 1, 'test', 1, 'automatic', ?)",
            (text_revision_id, digest),
        )
        structure_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO style_scenes "
            "(structure_revision_id, order_index, start_cp, end_cp) "
            "VALUES (?, 1, 0, 8)",
            (structure_id,),
        )
        scene_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO style_blocks "
            "(structure_revision_id, scene_id, order_index, paragraph_index, "
            "block_type, start_cp, end_cp) "
            "VALUES (?, ?, 1, 1, 'narration', 0, 2)",
            (structure_id, scene_id),
        )
        connection.execute(
            "INSERT INTO style_blocks "
            "(structure_revision_id, scene_id, order_index, paragraph_index, "
            "block_type, start_cp, end_cp) "
            "VALUES (?, ?, 2, 2, 'dialogue', 3, 8)",
            (structure_id, scene_id),
        )
        connection.commit()
        result = DocumentAnalysisOrchestrator(
            connection,
            model_client=_FakeModel(),
            model_provider="test",
            model_id="fake",
        ).analyze_document(
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
        )
        assert result.status == "succeeded"
        assert len(result.run_ids) == 10
        assert connection.execute(
            "SELECT COUNT(*) FROM style_analysis_runs WHERE document_id = ?",
            (document_id,),
        ).fetchone() == (10,)
        assert connection.execute(
            "SELECT COUNT(*) FROM style_annotations"
        ).fetchone() >= (5,)
    finally:
        connection.close()


def test_full_automatic_structure_materializes_semantic_structure(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        connection.execute("INSERT INTO works (slug, working_title) VALUES ('x', 'X')")
        work_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'c')",
            (work_id,),
        )
        chapter_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO episodes (work_id, chapter_id, position, title) "
            "VALUES (?, ?, 1, 'e')",
            (work_id, chapter_id),
        )
        episode_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO style_documents "
            "(kind, project_work_id, project_episode_id) VALUES "
            "('project_episode_draft', ?, ?)",
            (work_id, episode_id),
        )
        document_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        digest = "c" * 64
        connection.execute(
            "INSERT INTO style_text_revisions "
            "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
            "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
            "normalizer_id, normalizer_version) VALUES "
            "(?, 1, 1, ?, ?, ?, ?, ?, 'test', 1)",
            (
                document_id,
                "朝。\n\n「行こう」",
                "朝。\n\n「行こう」",
                digest,
                digest,
                digest,
            ),
        )
        text_revision_id = connection.execute("SELECT last_insert_rowid()").fetchone()[
            0
        ]
        connection.commit()

        result = DocumentAnalysisOrchestrator(
            connection,
            model_client=_FakeModel(boundary=True),
            model_provider="test",
            model_id="fake",
        ).analyze_document(
            document_id=document_id,
            text_revision_id=text_revision_id,
        )

        assert result.status == "succeeded"
        structure = connection.execute(
            "SELECT source_kind, parent_structure_revision_id, segmenter_id, "
            "segmenter_version "
            "FROM style_structure_revisions WHERE id = ?",
            (result.structure_revision_id,),
        ).fetchone()
        assert structure is not None
        assert structure[0] == "semantic"
        assert structure[1] is not None
        assert structure[2:4] == ("canonical-fiction-structure", 1)
        configs = dict(
            connection.execute(
                "SELECT analyzer_id, config_json FROM style_analysis_runs "
                "WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        )
        assert configs["scene-semantic-classifier"] == '{"scene_taxonomy_version":1}'
        assert configs["block-semantic-classifier"] == (
            '{"block_semantic_taxonomy_version":1}'
        )
        assert configs["pov-classifier"] == '{"pov_taxonomy_version":1}'
        basic_config = json.loads(configs["style-metrics-basic"])
        assert basic_config["metric_versions"]
        assert connection.execute(
            "SELECT COUNT(*) FROM style_structure_analysis_sources "
            "WHERE structure_revision_id = ?",
            (result.structure_revision_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT DISTINCT subject_type FROM style_annotations "
            "WHERE annotation_type = 'scene_boundary_candidate'"
        ).fetchone() == ("block",)
    finally:
        connection.close()
