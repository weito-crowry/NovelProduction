from __future__ import annotations

from typing import Any, cast

from novel_core.style_analysis.analysis_orchestrator_terms import reduce_term_novelty
from novel_core.style_analysis.analyzers.term_explanation import (
    detect_term_explanations,
)
from novel_core.style_analysis.analyzers.term_resolution import resolve_term_candidate
from novel_core.style_analysis.fingerprints import JsonValue
from novel_core.style_analysis.model_contracts import JsonObject
from novel_core.style_analysis.resumable_models import ResumableStageHost


class _FixedResponseClient:
    def __init__(self, response: JsonObject) -> None:
        self.response = response

    def complete_json(self, _request: Any) -> JsonObject:
        return self.response


def _int_value(value: object) -> int:
    return int(cast(Any, value))


class ResumableTermStagesMixin(ResumableStageHost):
    def _complete_deterministic_term(
        self, state: dict[str, Any], marker: dict[str, Any], run_id: int
    ) -> bool:
        term_id = _int_value(marker["term_id"])
        self.terms.repository.insert_mention(
            term_id=term_id,
            structure_revision_id=int(state["structure_revision_id"]),
            scene_id=_int_value(marker["scene_id"]),
            block_id=_int_value(marker["block_id"]),
            start_cp=_int_value(marker["start_cp"]),
            end_cp=_int_value(marker["end_cp"]),
            surface=str(marker["surface"]),
            analysis_run_id=run_id,
        )
        self._remember_resolved(
            state, "term_resolved_by_scene", _int_value(marker["scene_id"]), term_id
        )
        self._remember_novelty(state, term_id, str(marker["novelty"]), 1.0)
        return True

    @staticmethod
    def _remember_resolved(
        state: dict[str, Any], key: str, scene_id: int, identity_id: int
    ) -> None:
        values = cast(dict[str, list[int]], state.setdefault(key, {}))
        scene_values = values.setdefault(str(scene_id), [])
        if identity_id not in scene_values:
            scene_values.append(identity_id)

    @staticmethod
    def _remember_novelty(
        state: dict[str, Any], term_id: int, novelty: str, confidence: float
    ) -> None:
        values = cast(dict[str, list[JsonValue]], state.setdefault("term_novelty", {}))
        values.setdefault(str(term_id), []).append(
            cast(JsonValue, {"value": novelty, "confidence": confidence})
        )

    def _finish_term_resolution(self, state: dict[str, Any], run_id: int) -> None:
        values_by_term = cast(dict[str, list[JsonValue]], state.get("term_novelty", {}))
        for term_id_text, values in values_by_term.items():
            pairs: list[tuple[str, float]] = []
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("value"), str):
                    continue
                confidence = item.get("confidence")
                if isinstance(confidence, (int, float)) and not isinstance(
                    confidence, bool
                ):
                    pairs.append((str(item["value"]), float(confidence)))
            if not pairs:
                continue
            self.semantic.insert_raw(
                annotation_type="term.novelty",
                subject_type="term",
                subject_id=int(term_id_text),
                value={"value": reduce_term_novelty(tuple(item[0] for item in pairs))},
                confidence=min(item[1] for item in pairs),
                analysis_run_id=run_id,
            )

    def _apply_term_resolution(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        payload = cast(JsonObject, state.get("current_payload", {}))
        value = cast(JsonObject, payload["candidate"])
        decision = resolve_term_candidate(
            candidate=value,
            previous_blocks=cast(list[JsonObject], payload.get("previous_blocks", [])),
            subject_block=cast(JsonObject, payload.get("subject_block", {})),
            next_blocks=cast(list[JsonObject], payload.get("next_blocks", [])),
            candidates=cast(list[JsonObject], payload.get("candidates", [])),
            auto_merge_threshold=self.policy.term_resolution_auto_merge,
            client=_FixedResponseClient(response),
        )
        run_id = self._stage_run(state, "term_resolver")
        if run_id is None:
            raise ValueError("TERM_RESOLUTION_RUN_NOT_FOUND")
        if decision.decision == "unresolved":
            return
        scope = self.terms._scope(int(state["document_id"]))
        if decision.decision == "existing" and decision.term_id is not None:
            term = self.terms.repository.get(decision.term_id)
            term_id = term.id
            self.terms.insert_inferred_alias_if_missing(
                term_id=term_id,
                alias=str(value["surface"]),
                analysis_run_id=run_id,
            )
        else:
            term = self.terms.repository.create_inferred(
                reference_work_id=scope.get("reference_work_id"),
                document_id=scope.get("document_id"),
                canonical_label=cast(str, decision.new_canonical_label),
                term_type=cast(str, decision.new_term_type),
                run_id=run_id,
            )
            term_id = term.id
        block = cast(JsonObject, payload["subject_block"])
        block_id = _int_value(block["block_id"])
        start_cp = self._block_start(
            self.structure.list_blocks(int(state["structure_revision_id"])), block_id
        )
        self.terms.repository.insert_mention(
            term_id=term_id,
            structure_revision_id=int(state["structure_revision_id"]),
            scene_id=_int_value(block["scene_id"]),
            block_id=block_id,
            start_cp=start_cp + _int_value(value["start_in_block"]),
            end_cp=start_cp + _int_value(value["end_in_block"]),
            surface=str(value["surface"]),
            analysis_run_id=run_id,
        )
        scene_id = _int_value(block["scene_id"])
        self._remember_resolved(state, "term_resolved_by_scene", scene_id, term_id)
        self._remember_novelty(
            state,
            term_id,
            str(value.get("novelty_candidate", "uncertain")),
            decision.confidence,
        )

    def _apply_term_explanation(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        payload = cast(JsonObject, state.get("current_payload", {}))
        warnings: list[str] = []
        values = detect_term_explanations(
            term_mention_id=_int_value(payload["term_mention_id"]),
            term_label=str(payload["term_label"]),
            mention_block_id=_int_value(payload["mention_block_id"]),
            mention_start_in_block=_int_value(payload["mention_start_in_block"]),
            mention_end_in_block=_int_value(payload["mention_end_in_block"]),
            blocks=cast(list[JsonObject], payload.get("blocks", [])),
            client=_FixedResponseClient(response),
            warnings=warnings,
        )
        self._record_warnings(state, warnings)
        state["term_explanation_has_candidates"] = bool(values)
        if not values:
            return
        blocks = self.structure.list_blocks(int(state["structure_revision_id"]))
        mention_start = self._block_start(
            blocks, _int_value(payload["mention_block_id"])
        ) + _int_value(payload["mention_start_in_block"])
        selected = min(
            values,
            key=lambda candidate: (
                -int(candidate.completeness == "sufficient"),
                -candidate.confidence,
                abs(
                    self._block_start(blocks, candidate.block_id)
                    + candidate.start_in_block
                    - mention_start
                ),
                self._block_start(blocks, candidate.block_id)
                + candidate.start_in_block,
                self._block_start(blocks, candidate.block_id) + candidate.end_in_block,
            ),
        )
        run_id = self._stage_run(state, "term_explanation")
        if run_id is None:
            raise ValueError("TERM_EXPLANATION_RUN_NOT_FOUND")
        start = self._block_start(blocks, selected.block_id)
        self.semantic.insert_raw(
            annotation_type="term_explanation",
            subject_type="term_mention",
            subject_id=_int_value(payload["term_mention_id"]),
            value={
                "block_id": selected.block_id,
                "explanation_kind": selected.explanation_kind,
                "completeness": selected.completeness,
            },
            confidence=selected.confidence,
            analysis_run_id=run_id,
            start_cp=start + selected.start_in_block,
            end_cp=start + selected.end_in_block,
        )
