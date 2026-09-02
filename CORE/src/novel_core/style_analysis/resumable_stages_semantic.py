from __future__ import annotations

from typing import Any, cast

from novel_core.style_analysis.analyzers.block_semantics import classify_narration_block
from novel_core.style_analysis.analyzers.entity_mentions import extract_entity_mentions
from novel_core.style_analysis.analyzers.entity_resolution import resolve_entity_mention
from novel_core.style_analysis.analyzers.pov_classifier import classify_pov
from novel_core.style_analysis.analyzers.scene_boundary import detect_scene_boundaries
from novel_core.style_analysis.analyzers.scene_classifier import _reduce_labels
from novel_core.style_analysis.analyzers.speaker_attribution import attribute_speaker
from novel_core.style_analysis.analyzers.term_candidates import extract_term_candidates
from novel_core.style_analysis.fingerprints import JsonValue
from novel_core.style_analysis.model_contracts import JsonObject, validate_confidence
from novel_core.style_analysis.model_output_contracts import ResponseContractRegistry
from novel_core.style_analysis.resumable_models import (
    DocumentAnalysisRequest,
    ResumableStageHost,
)


class _FixedResponseClient:
    def __init__(self, response: JsonObject) -> None:
        self.response = response

    def complete_json(self, _request: Any) -> JsonObject:
        return self.response


class _SequenceResponseClient:
    def __init__(self, responses: list[JsonObject]) -> None:
        self._responses = iter(responses)

    def complete_json(self, _request: Any) -> JsonObject:
        try:
            return next(self._responses)
        except StopIteration as exc:
            raise ValueError("ANALYSIS_RESPONSE_COUNT_MISMATCH") from exc


def _int_value(value: object) -> int:
    return int(cast(Any, value))


class ResumableSemanticStagesMixin(ResumableStageHost):
    def _complete_deterministic_subject(
        self, state: dict[str, Any], stage: str
    ) -> bool:
        marker = state.pop("deterministic_subject", None)
        if not isinstance(marker, dict) or marker.get("stage") != stage:
            return False
        if marker.get("action") == "skip":
            return True
        run_id = self._stage_run(state, stage)
        if run_id is None:
            raise ValueError("DETERMINISTIC_RESOLUTION_RUN_NOT_FOUND")
        if stage == "entity_resolver":
            mention_id = _int_value(marker["mention_id"])
            entity_id = _int_value(marker["entity_id"])
            self.semantic.insert_raw(
                annotation_type="mention.entity_resolution",
                subject_type="mention",
                subject_id=mention_id,
                value={"entity_id": entity_id},
                confidence=1.0,
                analysis_run_id=run_id,
            )
            self._remember_resolved(
                state,
                "entity_resolved_by_scene",
                _int_value(marker["scene_id"]),
                entity_id,
            )
            return True
        if stage == "term_resolver":
            return self._complete_deterministic_term(state, marker, run_id)
        return False

    def _apply_model_response(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        stage = cast(str, state["stage"])
        if stage in {"scene_boundary", "entity_mentions", "term_candidates"}:
            return
        elif stage == "entity_resolver":
            self._apply_entity_resolution(state, response)
        elif stage == "speaker_attribution":
            self._apply_speaker(state, response)
        elif stage == "pov":
            self._apply_pov(state, response)
        elif stage == "term_resolver":
            self._apply_term_resolution(state, response)
        elif stage == "term_explanation":
            self._apply_term_explanation(state, response)
        elif stage == "scene_semantics" and state.get("stage_substage") != "reduce":
            pass
        elif stage == "scene_semantics" and state.get("stage_substage") == "reduce":
            classify_responses = [
                cast(JsonObject, value)
                for value in cast(list[JsonValue], state.get("stage_responses", []))
            ]
            self._apply_scene_semantics(
                state,
                {
                    "function": _reduce_labels(classify_responses, "function"),
                    "tone": _reduce_labels(classify_responses, "tone"),
                    "pace": response.get("pace"),
                    "information_load": response.get("information_load"),
                    "interaction": response.get("interaction"),
                },
            )
        elif stage == "block_semantics":
            self._apply_block_semantics(state, response)

    def _apply_scene_chunk_results(self, state: dict[str, Any]) -> None:
        if state.get("stage_errors"):
            return
        stage = cast(str, state["stage"])
        scene_id = state.get("stage_scene_id")
        if not isinstance(scene_id, int):
            raise ValueError("SCENE_STAGE_ID_NOT_FOUND")
        responses = [
            cast(JsonObject, value)
            for value in cast(list[JsonValue], state.get("stage_responses", []))
        ]
        if not responses:
            return
        structure_id = int(state["structure_revision_id"])
        revision = self.text.get_text_revision(
            int(state["document_id"]), int(state["text_revision_id"])
        )
        blocks = self.structure.list_blocks(structure_id)
        scene_blocks = [
            self._block_json(block, revision.canonical_text)
            for block in blocks
            if block.scene_id == scene_id
        ]
        client = _SequenceResponseClient(responses)
        run_id = self._stage_run(state, stage)
        if run_id is None:
            raise ValueError("SCENE_STAGE_RUN_NOT_FOUND")
        if stage == "scene_boundary":
            candidates = detect_scene_boundaries(
                base_structure_revision_id=structure_id,
                scene_id=scene_id,
                blocks=scene_blocks,
                client=client,
            )
            for candidate in candidates:
                self.semantic.insert_raw(
                    annotation_type="scene_boundary_candidate",
                    subject_type="block",
                    subject_id=candidate.after_block_id,
                    value={
                        "base_structure_revision_id": structure_id,
                        "reasons": list(candidate.reasons),
                    },
                    confidence=candidate.confidence,
                    analysis_run_id=run_id,
                )
            return
        if stage == "entity_mentions":
            mention_result = extract_entity_mentions(
                scene_id=scene_id,
                blocks=scene_blocks,
                previous_context_blocks=self._previous_context(
                    [
                        self._block_json(block, revision.canonical_text)
                        for block in blocks
                    ],
                    scene_id,
                ),
                client=client,
            )
            all_blocks = self.structure.list_blocks(structure_id)
            for mention_item in mention_result.items:
                start = self._block_start(all_blocks, mention_item.block_id)
                self.entities.repository.insert_mention(
                    structure_revision_id=structure_id,
                    scene_id=scene_id,
                    block_id=mention_item.block_id,
                    start_cp=start + mention_item.start_in_block,
                    end_cp=start + mention_item.end_in_block,
                    surface=mention_item.surface,
                    mention_type=mention_item.mention_type,
                    entity_type_candidate=mention_item.entity_type_candidate,
                    canonical_name_candidate=mention_item.canonical_name_candidate,
                    confidence=mention_item.confidence,
                    analysis_run_id=run_id,
                )
            self._record_warnings(state, mention_result.warnings)
            return
        if stage == "term_candidates":
            term_result = extract_term_candidates(
                scene_id=scene_id, blocks=scene_blocks, client=client
            )
            all_blocks = self.structure.list_blocks(structure_id)
            for term_item in term_result.items:
                self.semantic.insert_raw(
                    annotation_type="term_candidate",
                    subject_type="block",
                    subject_id=term_item.block_id,
                    value={
                        "surface": term_item.surface,
                        "canonical_label_candidate": (
                            term_item.canonical_label_candidate
                        ),
                        "term_type_candidate": term_item.term_type_candidate,
                        "novelty_candidate": term_item.novelty_candidate,
                    },
                    confidence=term_item.confidence,
                    analysis_run_id=run_id,
                    start_cp=self._block_start(all_blocks, term_item.block_id)
                    + term_item.start_in_block,
                    end_cp=self._block_start(all_blocks, term_item.block_id)
                    + term_item.end_in_block,
                )
            self._record_warnings(state, term_result.warnings)

    def _apply_entity_resolution(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        payload = cast(JsonObject, state.get("current_payload", {}))
        mention = cast(JsonObject, payload["mention"])
        candidates = cast(list[JsonObject], payload.get("candidates", []))
        decision = resolve_entity_mention(
            mention=mention,
            previous_blocks=cast(list[JsonObject], payload.get("previous_blocks", [])),
            subject_block=cast(JsonObject, payload.get("subject_block", {})),
            next_blocks=cast(list[JsonObject], payload.get("next_blocks", [])),
            candidates=candidates,
            auto_merge_threshold=self.policy.entity_resolution_auto_merge,
            client=_FixedResponseClient(response),
        )
        run_id = self._stage_run(state, "entity_resolver")
        if run_id is None:
            raise ValueError("ENTITY_RESOLUTION_RUN_NOT_FOUND")
        mention_id = _int_value(mention["mention_id"])
        if decision.decision == "existing" and decision.entity_id is not None:
            entity = self.entities.repository.get(decision.entity_id)
            self.semantic.insert_raw(
                annotation_type="mention.entity_resolution",
                subject_type="mention",
                subject_id=mention_id,
                value={"entity_id": entity.id},
                confidence=decision.confidence,
                analysis_run_id=run_id,
            )
            self.entities.insert_inferred_alias_if_missing(
                entity_id=entity.id,
                alias=str(mention["surface"]),
                alias_kind=_alias_kind(str(mention["mention_type"])),
                analysis_run_id=run_id,
                source_mention_id=mention_id,
            )
            self._remember_resolved(
                state,
                "entity_resolved_by_scene",
                _int_value(cast(JsonObject, payload["subject_block"])["scene_id"]),
                entity.id,
            )
        elif decision.decision == "new":
            scope = self.entities._scope(int(state["document_id"]))
            entity = self.entities.repository.create_inferred(
                reference_work_id=scope.get("reference_work_id"),
                document_id=scope.get("document_id"),
                entity_type=cast(str, decision.new_entity_type),
                canonical_name=cast(str, decision.new_canonical_name),
                run_id=run_id,
            )
            self.semantic.insert_raw(
                annotation_type="mention.entity_resolution",
                subject_type="mention",
                subject_id=mention_id,
                value={"entity_id": entity.id},
                confidence=decision.confidence,
                analysis_run_id=run_id,
            )
            self._remember_resolved(
                state,
                "entity_resolved_by_scene",
                _int_value(cast(JsonObject, payload["subject_block"])["scene_id"]),
                entity.id,
            )

    def _apply_speaker(self, state: dict[str, Any], response: JsonObject) -> None:
        payload = cast(JsonObject, state.get("current_payload", {}))
        value = attribute_speaker(
            previous_blocks=cast(list[JsonObject], payload.get("previous_blocks", [])),
            subject_block=cast(JsonObject, payload.get("subject_block", {})),
            next_blocks=cast(list[JsonObject], payload.get("next_blocks", [])),
            people=cast(list[JsonObject], payload.get("people", [])),
            client=_FixedResponseClient(response),
        )
        run_id = self._stage_run(state, "speaker_attribution")
        if run_id is None:
            raise ValueError("SPEAKER_RUN_NOT_FOUND")
        block = cast(JsonObject, payload["subject_block"])
        self.semantic.insert_raw(
            annotation_type="speaker",
            subject_type="block",
            subject_id=_int_value(block["block_id"]),
            value={
                "speaker_entity_id": value.speaker_entity_id,
                "evidence_block_ids": list(value.evidence_block_ids),
                "reason_code": value.reason_code,
            },
            confidence=value.confidence,
            analysis_run_id=run_id,
        )

    def _consume_completed(
        self,
        request: DocumentAnalysisRequest,
        state: dict[str, Any],
        completed: Any,
    ) -> None:
        expected = state.get("pending_call_key")
        if expected != completed.call_key:
            raise ValueError("ANALYSIS_CALL_KEY_MISMATCH")
        if "current_payload" not in state:
            self._restore_pending_payload(request, state, completed.call_key)
        stage = cast(str, state["stage"])
        if completed.response is None:
            state["stage_errors"] = True
            state["stage_error_code"] = completed.error_code or "FAILED"
            state["stage_error_message"] = (
                completed.error_message or completed.error_code or "FAILED"
            )
        else:
            contract_id = self._contract_for_completion(stage, state)
            ResponseContractRegistry.get(contract_id).validator(completed.response)
            try:
                self._apply_model_response(state, completed.response)
            except Exception as exc:
                state["stage_errors"] = True
                state["stage_error_code"] = type(exc).__name__
                state["stage_error_message"] = str(exc)
        self._advance_after_call(state, completed.response)
        state["pending_call_key"] = None

    def _restore_pending_payload(
        self,
        request: DocumentAnalysisRequest,
        state: dict[str, Any],
        call_key: str,
    ) -> None:
        stage = cast(str, state["stage"])
        prepared = (
            self._boundary_call(state)
            if stage == "scene_boundary"
            else self._model_stage_call(request, state)
        )
        if prepared is None or prepared.call_key != call_key:
            raise ValueError("ANALYSIS_CALL_KEY_MISMATCH")

    @staticmethod
    def _public_cursor(state: dict[str, Any]) -> JsonObject:
        cursor = dict(state)
        cursor.pop("current_payload", None)
        return cast(JsonObject, cursor)

    def _contract_for_completion(self, stage: str, state: dict[str, Any]) -> str:
        if stage == "scene_semantics" and state.get("stage_substage") == "reduce":
            return "style.scene_semantics.reduce.v1"
        return self._prompt_map[stage][2]

    def _advance_after_call(
        self, state: dict[str, Any], response: JsonObject | None
    ) -> None:
        stage = cast(str, state["stage"])
        if stage == "scene_boundary":
            self._advance_scene_chunks(state, response, boundary=True)
            return
        if stage == "term_explanation":
            if (
                response is not None
                and not state.get("stage_errors")
                and state.get("stage_substage") == "primary"
                and state.get("term_explanation_has_candidates") is False
                and state.get("stage_fallback_available") is True
            ):
                state["stage_substage"] = "fallback"
                return
            state["subject_index"] = int(state.get("subject_index", 0)) + 1
            state["stage_substage"] = "primary"
            return
        if stage in {"entity_mentions", "term_candidates", "scene_semantics"}:
            self._advance_scene_chunks(state, response, boundary=False)
            return
        state["subject_index"] = int(state.get("subject_index", 0)) + 1
        state["stage_substage"] = "classify"

    def _advance_scene_chunks(
        self, state: dict[str, Any], response: JsonObject | None, *, boundary: bool
    ) -> None:
        if response is not None and not (
            state.get("stage") == "scene_semantics"
            and state.get("stage_substage") == "reduce"
        ):
            values = cast(list[JsonValue], state.setdefault("stage_responses", []))
            values.append(cast(JsonValue, response))
        stage = cast(str, state["stage"])
        if stage == "scene_semantics" and state.get("stage_substage") == "reduce":
            state["stage_substage"] = "classify"

            state["stage_responses"] = []
            state["subject_index"] = int(state.get("subject_index", 0)) + 1
            return
        state["chunk_index"] = int(state.get("chunk_index", 0)) + 1
        request = DocumentAnalysisRequest(
            document_id=int(state["document_id"]),
            text_revision_id=int(state["text_revision_id"]),
            structure_revision_id=None,
            preset=str(state.get("preset", "full")),
        )
        spec = self._current_spec(stage, request, state)
        if spec is None and stage == "scene_semantics":
            responses = state.get("stage_responses", [])
            if len(cast(list[object], responses)) > 1:
                state["stage_substage"] = "reduce"
                state["chunk_index"] = 0
                return
        if spec is None:
            if stage in {"scene_boundary", "entity_mentions", "term_candidates"}:
                self._apply_scene_chunk_results(state)
            state["subject_index"] = int(state.get("subject_index", 0)) + 1
            state["chunk_index"] = 0
            if stage == "scene_semantics":
                responses = cast(list[JsonValue], state.get("stage_responses", []))
                if responses:
                    self._apply_scene_semantics(state, cast(JsonObject, responses[-1]))
            state["stage_responses"] = []
            state["stage_substage"] = "classify"

    def _apply_pov(self, state: dict[str, Any], response: JsonObject) -> None:
        payload = cast(JsonObject, state.get("current_payload", {}))
        value = classify_pov(
            scene_id=_int_value(payload["scene_id"]),
            blocks=cast(list[JsonObject], payload.get("blocks", [])),
            people=cast(list[JsonObject], payload.get("people", [])),
            client=_FixedResponseClient(response),
        )
        run_id = self._stage_run(state, "pov")
        if run_id is None:
            raise ValueError("POV_RUN_NOT_FOUND")
        self.semantic.insert_raw(
            annotation_type="scene.pov",
            subject_type="scene",
            subject_id=_int_value(payload["scene_id"]),
            value=value,
            confidence=validate_confidence(value["confidence"]),
            analysis_run_id=run_id,
        )

    def _apply_scene_semantics(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        payload = cast(JsonObject, state.get("current_payload", {}))
        scene_id = _int_value(payload.get("scene_id", 0))
        run_id = self._stage_run(state, "scene_semantics")
        if run_id is None:
            raise ValueError("SCENE_SEMANTIC_RUN_NOT_FOUND")
        for axis in ("function", "tone"):
            values = response.get(axis)
            if isinstance(values, list) and values:
                confidence = max(
                    validate_confidence(item["confidence"])
                    for item in values
                    if isinstance(item, dict)
                )
                self.semantic.insert_raw(
                    annotation_type=f"scene.{axis}",
                    subject_type="scene",
                    subject_id=scene_id,
                    value={"labels": values},
                    confidence=confidence,
                    analysis_run_id=run_id,
                )
        for axis in ("pace", "information_load", "interaction"):
            value = response.get(axis)
            if isinstance(value, dict):
                self.semantic.insert_raw(
                    annotation_type=f"scene.{axis}",
                    subject_type="scene",
                    subject_id=scene_id,
                    value=value,
                    confidence=validate_confidence(value["confidence"]),
                    analysis_run_id=run_id,
                )

    def _apply_block_semantics(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        payload = cast(JsonObject, state.get("current_payload", {}))
        value = classify_narration_block(
            block_id=_int_value(payload["block_id"]),
            text=str(payload["text"]),
            client=_FixedResponseClient(response),
        )
        run_id = self._stage_run(state, "block_semantics")
        if run_id is None:
            raise ValueError("BLOCK_SEMANTIC_RUN_NOT_FOUND")
        self.semantic.insert_raw(
            annotation_type="block.semantic_primary",
            subject_type="block",
            subject_id=_int_value(payload["block_id"]),
            value=value,
            confidence=validate_confidence(value["confidence"]),
            analysis_run_id=run_id,
        )


def _alias_kind(mention_type: str) -> str:
    return {
        "proper_name": "name",
        "alias": "nickname",
        "role_title": "role",
        "pronoun": "pronoun",
    }.get(mention_type, "name")
