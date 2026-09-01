from __future__ import annotations

import json
from pathlib import Path

from test_style_analysis_migration import open_test_database

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.semantic_metric_support import (
    enabled_person,
    resolve_entity_type,
    resolve_speaker,
)
from novel_core.style_analysis.semantic_metrics import calculate_semantic_metrics
from novel_core.style_analysis.semantic_repository import SemanticRepository
from novel_core.style_analysis.structure_models import BlockRecord, SceneRecord
from novel_core.style_analysis.term_repository import TermRepository


def _fixture(
    tmp_path: Path,
) -> tuple[object, int, tuple[SceneRecord, ...], tuple[BlockRecord, ...]]:
    connection = open_test_database(tmp_path / "story.db")
    connection.execute("INSERT INTO works (slug, working_title) VALUES ('x', 'X')")
    work_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, 'c')",
        (work_id,),
    )
    chapter_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO episodes (work_id, chapter_id, position, title) "
        "VALUES (?, ?, 1, 'e')",
        (work_id, chapter_id),
    )
    episode_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_documents (kind, project_work_id, project_episode_id) "
        "VALUES ('project_episode_draft', ?, ?)",
        (work_id, episode_id),
    )
    document_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    text = "「本当？」\n動く"
    digest = "c" * 64
    connection.execute(
        "INSERT INTO style_text_revisions "
        "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
        "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
        "normalizer_id, normalizer_version) VALUES (?, 1, 1, ?, ?, ?, ?, ?, 'test', 1)",
        (document_id, text, text, digest, digest, digest),
    )
    text_revision_id = int(
        connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    )
    connection.execute(
        "INSERT INTO style_structure_revisions "
        "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
        "source_kind, fingerprint) VALUES (?, 1, 'test', 1, 'manual', ?)",
        (text_revision_id, digest),
    )
    structure_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_scenes "
        "(structure_revision_id, order_index, start_cp, end_cp) VALUES (?, 1, 0, 8)",
        (structure_id,),
    )
    scene_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_blocks "
        "(structure_revision_id, scene_id, order_index, paragraph_index, "
        "block_type, start_cp, end_cp) VALUES (?, ?, 1, 1, 'dialogue', 0, 5)",
        (structure_id, scene_id),
    )
    dialogue_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_blocks "
        "(structure_revision_id, scene_id, order_index, paragraph_index, "
        "block_type, start_cp, end_cp) VALUES (?, ?, 2, 2, 'narration', 6, 8)",
        (structure_id, scene_id),
    )
    narration_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    connection.execute(
        "INSERT INTO style_entities "
        "(document_id, entity_type, canonical_name, origin) "
        "VALUES (?, 'person', 'A', 'manual')",
        (document_id,),
    )
    person_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
    runs = AnalysisRunRepository(connection)
    resolver_id = runs.insert_run(
        document_id=document_id,
        analyzer_id="entity-resolver",
        analyzer_version=1,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_id,
        status="succeeded",
        fingerprint="d" * 64,
        config_json="{}",
        started_at="2026-09-01T00:00:00+00:00",
    )
    speaker_id = runs.insert_run(
        document_id=document_id,
        analyzer_id="speaker-attribution",
        analyzer_version=1,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_id,
        status="succeeded",
        fingerprint="e" * 64,
        config_json="{}",
        started_at="2026-09-01T00:00:00+00:00",
    )
    block_id = runs.insert_run(
        document_id=document_id,
        analyzer_id="block-semantic-classifier",
        analyzer_version=1,
        text_revision_id=text_revision_id,
        structure_revision_id=structure_id,
        status="succeeded",
        fingerprint="f" * 64,
        config_json="{}",
        started_at="2026-09-01T00:00:00+00:00",
    )
    runs.add_dependency(speaker_id, resolver_id)
    semantic = SemanticRepository(connection)
    semantic.insert_annotation(
        annotation_type="mention.entity_resolution",
        subject_type="mention",
        subject_id=1,
        value_json=json.dumps({"entity_id": person_id}),
        confidence=1.0,
        analysis_run_id=resolver_id,
    )
    semantic.insert_annotation(
        annotation_type="speaker",
        subject_type="block",
        subject_id=dialogue_id,
        value_json=json.dumps(
            {"speaker_entity_id": person_id, "reason_code": "explicit_speech_tag"}
        ),
        confidence=0.9,
        analysis_run_id=speaker_id,
    )
    semantic.insert_annotation(
        annotation_type="block.semantic_primary",
        subject_type="block",
        subject_id=narration_id,
        value_json=json.dumps({"label": "action"}),
        confidence=0.9,
        analysis_run_id=block_id,
    )
    connection.commit()
    scenes = (SceneRecord(scene_id, structure_id, 1, 0, 8),)
    blocks = (
        BlockRecord(dialogue_id, structure_id, scene_id, 1, 1, "dialogue", 0, 5),
        BlockRecord(narration_id, structure_id, scene_id, 2, 2, "narration", 6, 8),
    )
    return connection, document_id, scenes, blocks


def test_semantic_metrics_use_registry_effective_values_and_outer_quotes(
    tmp_path: Path,
) -> None:
    connection, document_id, scenes, blocks = _fixture(tmp_path)
    try:
        result = calculate_semantic_metrics(
            connection,
            document_id=document_id,
            canonical_text="「本当？」\n動く",
            scenes=scenes,
            blocks=blocks,
            speaker_run_id=2,
            term_run_id=None,
            explanation_run_id=None,
            block_run_id=3,
        )
        values = {
            (item.target_type, item.metric_name): item.value
            for item in result.measurements
        }
        assert values[("document", "semantic.action.char_ratio")] == 2 / 7
        assert values[("character", "speaker.utterance_count")] == 1
        assert values[("character", "speaker.utterance_len.p50")] == 3
        assert values[("character", "speaker.question_ratio")] == 1
    finally:
        connection.close()


def test_effective_entity_type_controls_character_metrics(tmp_path: Path) -> None:
    connection, document_id, scenes, blocks = _fixture(tmp_path)
    try:
        person_id = connection.execute(
            "SELECT id FROM style_entities WHERE canonical_name = 'A'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE style_entities SET entity_type = 'other' WHERE id = ?",
            (person_id,),
        )
        connection.execute(
            "INSERT INTO style_manual_overrides "
            "(document_id, subject_type, subject_id, field_path, operation, "
            "value_json, structure_revision_id) VALUES (?, 'entity', ?, "
            "'entity.entity_type', 'set', '\"person\"', 1)",
            (document_id, person_id),
        )
        assert resolve_entity_type(connection, person_id).value == "person"
        assert enabled_person(connection, person_id)
        result = calculate_semantic_metrics(
            connection,
            document_id=document_id,
            canonical_text="「本当？」\n動く",
            scenes=scenes,
            blocks=blocks,
            speaker_run_id=2,
            term_run_id=None,
            explanation_run_id=None,
            block_run_id=3,
        )
        assert any(
            item.target_type == "character" and item.target_id == person_id
            for item in result.measurements
        )

        connection.execute(
            "INSERT INTO style_manual_overrides "
            "(document_id, subject_type, subject_id, field_path, operation, "
            "value_json, structure_revision_id) VALUES (?, 'entity', ?, "
            "'entity.entity_type', 'set', '\"other\"', 1)",
            (document_id, person_id),
        )
        assert resolve_entity_type(connection, person_id).value == "other"
        assert not enabled_person(connection, person_id)
        result = calculate_semantic_metrics(
            connection,
            document_id=document_id,
            canonical_text="「本当？」\n動く",
            scenes=scenes,
            blocks=blocks,
            speaker_run_id=2,
            term_run_id=None,
            explanation_run_id=None,
            block_run_id=3,
        )
        assert not any(item.target_type == "character" for item in result.measurements)
    finally:
        connection.close()


def test_incomplete_first_appearance_suppresses_term_metrics(tmp_path: Path) -> None:
    connection, document_id, scenes, blocks = _fixture(tmp_path)
    try:
        result = calculate_semantic_metrics(
            connection,
            document_id=document_id,
            canonical_text="「本当？」\n動く",
            scenes=scenes,
            blocks=blocks,
            speaker_run_id=None,
            term_run_id=None,
            explanation_run_id=None,
            block_run_id=None,
            term_first_appearance_complete=False,
        )
        assert not any(
            item.metric_name.startswith("term.") for item in result.measurements
        )
        assert result.partial
    finally:
        connection.close()


def test_composition_metrics_emit_zero_for_dialogue_only_scope(tmp_path: Path) -> None:
    connection, document_id, scenes, blocks = _fixture(tmp_path)
    try:
        dialogue_only = tuple(
            block for block in blocks if block.block_type == "dialogue"
        )
        result = calculate_semantic_metrics(
            connection,
            document_id=document_id,
            canonical_text="「本当？」",
            scenes=scenes,
            blocks=dialogue_only,
            speaker_run_id=None,
            term_run_id=None,
            explanation_run_id=None,
            block_run_id=3,
        )
        composition = [
            item
            for item in result.measurements
            if item.metric_name.startswith("semantic.")
        ]
        assert len(composition) == 10
        assert {item.value for item in composition} == {0.0}
        assert {item.sample_count for item in composition} == {1}
    finally:
        connection.close()


def test_term_metrics_use_first_mentions_and_sufficient_explanation(
    tmp_path: Path,
) -> None:
    connection, document_id, scenes, blocks = _fixture(tmp_path)
    try:
        runs = AnalysisRunRepository(connection)
        term_run_id = runs.insert_run(
            document_id=document_id,
            analyzer_id="term-resolver",
            analyzer_version=1,
            text_revision_id=1,
            structure_revision_id=1,
            status="succeeded",
            fingerprint="1" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        explanation_run_id = runs.insert_run(
            document_id=document_id,
            analyzer_id="term-explanation-detector",
            analyzer_version=1,
            text_revision_id=1,
            structure_revision_id=1,
            status="succeeded",
            fingerprint="2" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        cursor = connection.execute(
            "INSERT INTO style_terms "
            "(document_id, canonical_label, term_type, origin) "
            "VALUES (?, '動く', 'other', 'manual')",
            (document_id,),
        )
        assert cursor.lastrowid is not None
        term_id = int(cursor.lastrowid)
        mention = TermRepository(connection).insert_mention(
            term_id=term_id,
            structure_revision_id=1,
            scene_id=scenes[0].id,
            block_id=blocks[1].id,
            start_cp=6,
            end_cp=8,
            surface="動く",
            analysis_run_id=term_run_id,
        )
        semantic = SemanticRepository(connection)
        semantic.insert_annotation(
            annotation_type="term.novelty",
            subject_type="term",
            subject_id=term_id,
            value_json='{"value":"work_specific"}',
            confidence=1.0,
            analysis_run_id=term_run_id,
        )
        semantic.insert_annotation(
            annotation_type="term_explanation",
            subject_type="term_mention",
            subject_id=mention.id,
            value_json=json.dumps(
                {"block_id": blocks[1].id, "completeness": "sufficient"}
            ),
            confidence=0.9,
            analysis_run_id=explanation_run_id,
            start_cp=6,
            end_cp=8,
        )
        connection.commit()
        result = calculate_semantic_metrics(
            connection,
            document_id=document_id,
            canonical_text="「本当？」\n動く",
            scenes=scenes,
            blocks=blocks,
            speaker_run_id=None,
            term_run_id=term_run_id,
            explanation_run_id=explanation_run_id,
            block_run_id=None,
        )
        values = {
            (item.target_type, item.metric_name): item.value
            for item in result.measurements
        }
        assert values[("document", "term.new_per_1000_chars")] == 1000 / 7
        assert values[("scene", "term.explained_same_scene_ratio")] == 1
        assert values[("document", "term.explanation_delay.p50")] == 0
    finally:
        connection.close()


def test_confirmed_and_manual_speaker_values_use_registry_field_paths(
    tmp_path: Path,
) -> None:
    connection, document_id, _, blocks = _fixture(tmp_path)
    try:
        person_id = connection.execute(
            "SELECT id FROM style_entities WHERE document_id = ?", (document_id,)
        ).fetchone()[0]
        raw = (json.dumps({"speaker_entity_id": person_id}), 0.1, None)
        connection.execute(
            "INSERT INTO style_inference_reviews "
            "(document_id, subject_type, subject_id, field_path, analysis_run_id, "
            "review_status) VALUES (?, 'block', ?, 'block.speaker', 2, 'confirmed')",
            (document_id, blocks[0].id),
        )
        confirmed = resolve_speaker(connection, blocks[0].id, 2, raw, 0.85)
        assert confirmed.value == person_id

        connection.execute(
            "INSERT INTO style_manual_overrides "
            "(document_id, subject_type, subject_id, field_path, operation, "
            "value_json) "
            "VALUES (?, 'block', ?, 'block.speaker_entity_id', 'set', ?)",
            (document_id, blocks[0].id, json.dumps(person_id)),
        )
        manual = resolve_speaker(connection, blocks[0].id, 2, None, 0.85)
        assert manual.value == person_id
    finally:
        connection.close()


def test_term_explained_ratio_has_no_row_for_zero_denominator(tmp_path: Path) -> None:
    connection, document_id, scenes, blocks = _fixture(tmp_path)
    try:
        run_id = AnalysisRunRepository(connection).insert_run(
            document_id=document_id,
            analyzer_id="term-resolver",
            analyzer_version=1,
            text_revision_id=1,
            structure_revision_id=1,
            status="succeeded",
            fingerprint="3" * 64,
            config_json="{}",
            started_at="2026-09-01T00:00:00+00:00",
        )
        result = calculate_semantic_metrics(
            connection,
            document_id=document_id,
            canonical_text="「本当？」\n動く",
            scenes=scenes,
            blocks=blocks,
            speaker_run_id=None,
            term_run_id=run_id,
            explanation_run_id=None,
            block_run_id=None,
        )
        assert all(
            item.metric_name != "term.explained_same_scene_ratio"
            for item in result.measurements
        )
        assert all(
            item.sample_count == 0
            for item in result.measurements
            if item.metric_name == "term.new_per_1000_chars"
        )
    finally:
        connection.close()
