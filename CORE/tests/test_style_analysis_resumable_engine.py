from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any, cast

from test_style_analysis_migration import open_test_database

from novel_core.style_analysis.analysis_orchestrator import (
    DocumentAnalysisOrchestrator,
)
from novel_core.style_analysis.model_contracts import ModelRequest
from novel_core.style_analysis.resumable_engine import ResumableDocumentAnalysisEngine
from novel_core.style_analysis.resumable_models import (
    CompletedModelCall,
    DocumentAnalysisRequest,
)
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


def _large_scene_document(connection: sqlite3.Connection) -> tuple[int, int, int, int]:
    document_id, text_id = _document(connection)
    structure_id = int(
        connection.execute(
            "SELECT id FROM style_structure_revisions WHERE text_revision_id = ?",
            (text_id,),
        ).fetchone()[0]
    )
    scene_id = int(
        connection.execute(
            "SELECT id FROM style_scenes WHERE structure_revision_id = ?",
            (structure_id,),
        ).fetchone()[0]
    )
    first_block_id = int(
        connection.execute(
            "SELECT id FROM style_blocks WHERE structure_revision_id = ? "
            "ORDER BY order_index LIMIT 1",
            (structure_id,),
        ).fetchone()[0]
    )
    text = "a" * 16000 + "b" * 16000
    connection.execute(
        "UPDATE style_text_revisions SET raw_text = ?, canonical_text = ? WHERE id = ?",
        (text, text, text_id),
    )
    connection.execute(
        "UPDATE style_scenes SET end_cp = ? WHERE id = ?", (len(text), scene_id)
    )
    connection.execute(
        "UPDATE style_blocks SET end_cp = ? WHERE id = ?", (16000, first_block_id)
    )
    connection.execute(
        "INSERT INTO style_blocks "
        "(structure_revision_id, scene_id, order_index, paragraph_index, block_type, "
        "start_cp, end_cp) VALUES (?, ?, 2, 2, 'narration', ?, ?)",
        (structure_id, scene_id, 16000, len(text)),
    )
    connection.commit()
    return document_id, text_id, structure_id, scene_id


def _semantic_response(contract_id: str, mode: str | None = None) -> dict[str, object]:
    label = {"label": "unclear", "confidence": 0.1}
    if contract_id == "style.pov.v1":
        return {"pov_mode": "unclear", "pov_entity_id": None, "confidence": 0.1}
    if contract_id == "style.scene_semantics.reduce.v1" or mode == "reduce":
        return {
            "pace": label,
            "information_load": label,
            "interaction": label,
        }
    if contract_id == "style.scene_semantics.classify.v1":
        return {
            "function": [label],
            "tone": [label],
            "pace": label,
            "information_load": label,
            "interaction": label,
        }
    raise AssertionError(contract_id)


def test_resumable_engine_preserves_scene_and_pov_multi_chunk_contract_after_restart(
    tmp_path: Path,
) -> None:
    connection = open_test_database(tmp_path / "story.db")
    try:
        document_id, text_id, structure_id, scene_id = _large_scene_document(connection)
        request = DocumentAnalysisRequest(
            document_id=document_id,
            text_revision_id=text_id,
            structure_revision_id=structure_id,
        )
        cursor = {"schema_version": 1}
        completed: CompletedModelCall | None = None
        calls: list[object] = []
        result = None
        while result is None:
            engine = ResumableDocumentAnalysisEngine(
                connection,
                model_provider="chatgpt_mcp",
                model_id="gpt-test",
                policy=AnalysisPolicy(),
            )
            advanced = engine.advance(request, cursor, completed)
            cursor = advanced.cursor
            if advanced.result is not None:
                result = advanced.result
                break
            assert advanced.pending_call is not None
            call = advanced.pending_call
            calls.append(call)
            mode = call.user_payload.get("mode")
            if call.response_contract_id in {
                "style.scene_semantics.classify.v1",
                "style.scene_semantics.reduce.v1",
            }:
                response = _semantic_response(call.response_contract_id, str(mode))
            elif call.response_contract_id == "style.pov.v1":
                response = _semantic_response(call.response_contract_id)
            elif call.response_contract_id == "style.entity_mentions.v1":
                response = {"mentions": []}
            elif call.response_contract_id == "style.term_candidates.v1":
                response = {"terms": []}
            elif call.response_contract_id == "style.block_semantic.v1":
                response = {"label": "unclear", "confidence": 0.1}
            else:
                raise AssertionError(call.response_contract_id)
            completed = CompletedModelCall(call_key=call.call_key, response=response)

        pov_calls = [call for call in calls if call.analyzer_id == "pov-classifier"]
        assert [call.user_payload.get("mode") for call in pov_calls] == [
            "classify",
            "classify",
            "reduce",
        ]
        assert pov_calls[-1].user_payload.get("scene_id") is None
        assert len(pov_calls[-1].user_payload["chunks"]) == 2
        semantic_calls = [
            call for call in calls if call.analyzer_id == "scene-semantic-classifier"
        ]
        assert [call.user_payload.get("mode") for call in semantic_calls] == [
            "classify",
            "classify",
            "reduce",
        ]
        assert result.status == "succeeded"
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_annotations "
                "WHERE annotation_type IN ("
                "'scene.pov', 'scene.function', 'scene.tone', 'scene.pace', "
                "'scene.information_load', 'scene.interaction') "
                "AND subject_id = ?",
                (scene_id,),
            ).fetchone()[0]
            == 6
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_annotations WHERE subject_id = 0"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM style_analysis_runs WHERE status != 'succeeded'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


class _ParityModel:
    def __init__(self) -> None:
        self.calls: list[ModelRequest] = []

    def complete_json(self, request: ModelRequest) -> dict[str, object]:
        self.calls.append(request)
        payload = request.user_payload
        if request.prompt_id == "style.scene_boundary":
            return {"boundaries": []}
        if request.prompt_id == "style.entity_mentions":
            block = cast(dict[str, Any], cast(list[Any], payload["blocks"])[0])
            block_text = str(block["text"])
            start = block_text.index("Alice")
            return {
                "mentions": [
                    {
                        "block_id": block["block_id"],
                        "surface": "Alice",
                        "start_in_block": start,
                        "end_in_block": start + len("Alice"),
                        "mention_type": "proper_name",
                        "entity_type_candidate": "person",
                        "canonical_name_candidate": "Alice",
                        "confidence": 0.9,
                    }
                ]
            }
        if request.prompt_id == "style.entity_resolution":
            return {
                "decision": "new",
                "entity_id": None,
                "new_entity_type": "person",
                "new_canonical_name": "Alice",
                "confidence": 0.9,
            }
        if request.prompt_id == "style.speaker_attribution":
            return {
                "speaker_entity_id": None,
                "confidence": 0.1,
                "evidence_block_ids": [],
                "reason_code": "unknown",
            }
        if request.prompt_id == "style.pov":
            return {"pov_mode": "unclear", "pov_entity_id": None, "confidence": 0.2}
        if request.prompt_id == "style.term_candidates":
            block = cast(dict[str, Any], cast(list[Any], payload["blocks"])[0])
            block_text = str(block["text"])
            start = block_text.index("Magic")
            return {
                "terms": [
                    {
                        "block_id": block["block_id"],
                        "surface": "Magic",
                        "start_in_block": start,
                        "end_in_block": start + len("Magic"),
                        "canonical_label_candidate": "Magic",
                        "term_type_candidate": "world_term",
                        "novelty_candidate": "work_specific",
                        "confidence": 0.9,
                    }
                ]
            }
        if request.prompt_id == "style.term_resolution":
            return {
                "decision": "new",
                "term_id": None,
                "new_term_type": "world_term",
                "new_canonical_label": "Magic",
                "confidence": 0.9,
            }
        if request.prompt_id == "style.term_explanation":
            return {"explanations": []}
        if request.prompt_id == "style.scene_semantics":
            value = {"label": "unclear", "confidence": 0.2}
            return {
                "function": [value],
                "tone": [value],
                "pace": {"label": "medium", "confidence": 0.2},
                "information_load": {"label": "low", "confidence": 0.2},
                "interaction": {"label": "dialogue", "confidence": 0.2},
            }
        if request.prompt_id == "style.block_semantic":
            return {"label": "description", "confidence": 0.2}
        raise AssertionError(request.prompt_id)


def _parity_document(path: Path) -> tuple[int, int]:
    connection = open_test_database(path)
    try:
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
        document_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        digest = "c" * 64
        text = "Alice sees Magic.\n\n「Alice says」"
        connection.execute(
            "INSERT INTO style_text_revisions "
            "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
            "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
            "normalizer_id, normalizer_version) "
            "VALUES (?, 1, 1, ?, ?, ?, ?, ?, 'test', 1)",
            (document_id, text, text, digest, digest, digest),
        )
        text_revision_id = int(
            connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        connection.commit()
        return document_id, text_revision_id
    finally:
        connection.close()


def _analysis_rows(connection: sqlite3.Connection) -> dict[str, list[tuple[Any, ...]]]:
    return {
        "entities": connection.execute(
            "SELECT entity_type, canonical_name, origin FROM style_entities ORDER BY id"
        ).fetchall(),
        "mentions": connection.execute(
            "SELECT scene_id, block_id, start_cp, end_cp, surface, mention_type, "
            "entity_type_candidate, canonical_name_candidate, confidence "
            "FROM style_mentions ORDER BY id"
        ).fetchall(),
        "terms": connection.execute(
            "SELECT canonical_label, term_type, origin FROM style_terms ORDER BY id"
        ).fetchall(),
        "term_mentions": connection.execute(
            "SELECT term_id, scene_id, block_id, start_cp, end_cp, surface "
            "FROM style_term_mentions ORDER BY id"
        ).fetchall(),
        "annotations": connection.execute(
            "SELECT annotation_type, subject_type, subject_id, value_json, "
            "confidence, start_cp, end_cp FROM style_annotations ORDER BY id"
        ).fetchall(),
        "runs": connection.execute(
            "SELECT analyzer_id, status, warning_json, error_code "
            "FROM style_analysis_runs ORDER BY id"
        ).fetchall(),
    }


def test_internal_and_external_drivers_have_ten_analyzer_parity(
    tmp_path: Path,
) -> None:
    internal_path = tmp_path / "internal.db"
    document_id, text_revision_id = _parity_document(internal_path)
    external_path = tmp_path / "external.db"
    shutil.copyfile(internal_path, external_path)

    internal_connection = sqlite3.connect(internal_path)
    try:
        internal_model = _ParityModel()
        internal_result = DocumentAnalysisOrchestrator(
            internal_connection,
            model_client=internal_model,
            model_provider="test",
            model_id="fake",
        ).analyze_document(
            document_id=document_id,
            text_revision_id=text_revision_id,
            preset="full",
        )
        internal_connection.commit()
        internal_calls = [
            (call.prompt_id, call.prompt_version, call.user_payload)
            for call in internal_model.calls
        ]
        internal_rows = _analysis_rows(internal_connection)
    finally:
        internal_connection.close()

    external_connection = sqlite3.connect(external_path)
    try:
        cursor = {"schema_version": 1}
        completed: CompletedModelCall | None = None
        external_calls = []
        external_result = None
        while external_result is None:
            advanced = ResumableDocumentAnalysisEngine(
                external_connection,
                model_provider="test",
                model_id="fake",
                policy=AnalysisPolicy(),
            ).advance(
                DocumentAnalysisRequest(document_id, text_revision_id),
                cursor,
                completed,
            )
            cursor = advanced.cursor
            if advanced.result is not None:
                external_result = advanced.result
                break
            assert advanced.pending_call is not None
            call = advanced.pending_call
            external_calls.append(
                (call.prompt_id, call.prompt_version, call.user_payload)
            )
            response = _ParityModel().complete_json(
                ModelRequest(
                    call.prompt_id,
                    call.prompt_version,
                    call.system_prompt,
                    call.user_payload,
                )
            )
            completed = CompletedModelCall(call_key=call.call_key, response=response)
        external_connection.commit()
        external_rows = _analysis_rows(external_connection)
    finally:
        external_connection.close()

    assert internal_result.status == external_result.status == "succeeded"
    assert internal_result.metrics == external_result.metrics
    assert internal_calls == external_calls
    assert [call[0] for call in internal_calls] == [
        "style.scene_boundary",
        "style.entity_mentions",
        "style.entity_resolution",
        "style.speaker_attribution",
        "style.pov",
        "style.term_candidates",
        "style.term_resolution",
        "style.term_explanation",
        "style.scene_semantics",
        "style.block_semantic",
    ]
    assert internal_rows == external_rows
