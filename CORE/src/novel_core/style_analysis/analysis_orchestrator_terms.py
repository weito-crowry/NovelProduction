from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from novel_core.errors import AnalysisCancelledError
from novel_core.style_analysis.analyzers.block_semantics import (
    classify_narration_blocks,
)
from novel_core.style_analysis.analyzers.scene_classifier import classify_scene
from novel_core.style_analysis.analyzers.term_explanation import (
    detect_term_explanations,
)
from novel_core.style_analysis.analyzers.term_resolution import resolve_term_candidate
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.model_contracts import (
    JsonObject as ModelJsonObject,
)
from novel_core.style_analysis.model_contracts import ModelClient, validate_confidence
from novel_core.style_analysis.resolver_candidates import build_identity_shortlist
from novel_core.style_analysis.structure_models import BlockRecord, SceneRecord


def reduce_term_novelty(values: Sequence[str]) -> str:
    concrete = {value for value in values if value != "uncertain"}
    return next(iter(concrete)) if len(concrete) == 1 else "uncertain"


class TermAndSceneAnalysisMixin:
    def _resolve_terms(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        blocks: Sequence[BlockRecord],
        candidate_run: int,
    ) -> int:
        scope = self.terms._scope(document_id)
        registry = self.terms.candidate_rows(
            document_id=document_id,
            term_type="other",
            same_scene_ids=set(),
        )
        run_id = self._new_run(
            "term-resolver",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            dependencies=(candidate_run,),
            state_fingerprint=fingerprint_json(
                cast(
                    JsonValue,
                    {
                        "scope": scope,
                        "term_registry_state": self._term_registry_state(document_id),
                    },
                )
            ),
            policy_inputs=("term_resolution_auto_merge",),
            registry_input_fingerprint=fingerprint_json(cast(JsonValue, registry)),
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        block_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        try:
            if self._is_reused(run_id):
                return int(run_id)
            annotations = self.semantic.repository.list_for_run(candidate_run)
            resolved_by_scene: dict[int, set[int]] = {}
            novelty_by_term: dict[int, list[tuple[str, float]]] = {}
            for annotation in annotations:
                self._safe_point()
                if annotation.annotation_type != "term_candidate":
                    continue
                value = json.loads(annotation.value_json)
                if not isinstance(value, dict):
                    continue
                previous, subject, following = self._context(
                    block_json, annotation.subject_id, 2, 2
                )
                exact = self.terms.exact_matches(
                    document_id=document_id, surface=str(value["surface"])
                )
                if len(exact) == 1:
                    term_id, confidence = exact[0].id, 1.0
                elif len(exact) > 1:
                    continue
                else:
                    candidates = self.terms.candidate_rows(
                        document_id=document_id,
                        term_type=str(value["term_type_candidate"]),
                        same_scene_ids=resolved_by_scene.get(
                            self._block_scene(blocks, annotation.subject_id), set()
                        ),
                    )
                    candidates = build_identity_shortlist(
                        surface=str(value["surface"]),
                        canonical_name=str(value["canonical_label_candidate"]),
                        candidate_type=str(value["term_type_candidate"]),
                        identities=candidates,
                        same_scene_ids=resolved_by_scene.get(
                            self._block_scene(blocks, annotation.subject_id), set()
                        ),
                        id_key="term_id",
                        type_key="term_type",
                        name_key="canonical_label",
                    )
                    decision = resolve_term_candidate(
                        candidate={
                            "surface": value["surface"],
                            "canonical_label_candidate": value[
                                "canonical_label_candidate"
                            ],
                            "term_type_candidate": value["term_type_candidate"],
                        },
                        previous_blocks=previous,
                        subject_block=subject,
                        next_blocks=following,
                        candidates=candidates,
                        auto_merge_threshold=self.policy.term_resolution_auto_merge,
                        client=cast(ModelClient, self._analysis_client),
                    )
                    if decision.decision == "unresolved":
                        continue
                    if decision.decision == "existing" and decision.term_id is not None:
                        term = self.terms.repository.get(decision.term_id)
                        term_id, confidence = decision.term_id, decision.confidence
                        self.terms.insert_inferred_alias_if_missing(
                            term_id=term.id,
                            alias=str(value["surface"]),
                            analysis_run_id=run_id,
                        )
                    elif decision.new_term_type and decision.new_canonical_label:
                        term = self.terms.repository.create_inferred(
                            reference_work_id=scope.get("reference_work_id"),
                            document_id=scope.get("document_id"),
                            canonical_label=decision.new_canonical_label,
                            term_type=decision.new_term_type,
                            run_id=run_id,
                        )
                        term_id, confidence = term.id, decision.confidence
                    else:
                        continue
                self.terms.repository.insert_mention(
                    term_id=term_id,
                    structure_revision_id=structure_id,
                    scene_id=self._block_scene(blocks, annotation.subject_id),
                    block_id=annotation.subject_id,
                    start_cp=annotation.start_cp or 0,
                    end_cp=annotation.end_cp or 0,
                    surface=str(value["surface"]),
                    analysis_run_id=run_id,
                )
                scene_id = self._block_scene(blocks, annotation.subject_id)
                resolved_by_scene.setdefault(scene_id, set()).add(term_id)
                novelty = str(value.get("novelty_candidate", "uncertain"))
                values = novelty_by_term.setdefault(term_id, [])
                values.append((novelty, confidence))
            for term_id, values in novelty_by_term.items():
                reduced = reduce_term_novelty(tuple(item[0] for item in values))
                self.semantic.insert_raw(
                    annotation_type="term.novelty",
                    subject_type="term",
                    subject_id=term_id,
                    value={"value": reduced},
                    confidence=min(item[1] for item in values),
                    analysis_run_id=run_id,
                )
            self._finish(run_id)
        except AnalysisCancelledError as exc:
            self._finish(run_id, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return int(run_id)

    def _explanations(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        blocks: Sequence[BlockRecord],
        dependency: int,
    ) -> int:
        run_id = self._new_run(
            "term-explanation-detector",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            dependencies=(dependency,),
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        block_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        explanation_warnings: list[str] = []
        try:
            if self._is_reused(run_id):
                return int(run_id)
            for mention in self.terms.repository.list_mentions(
                analysis_run_id=dependency
            ):
                self._safe_point()
                term = self.terms.repository.get(mention.term_id)
                scene_blocks = [
                    block
                    for block in block_json
                    if block.get("scene_id") == mention.scene_id
                ]
                position = next(
                    (
                        index
                        for index, block in enumerate(scene_blocks)
                        if block.get("block_id") == mention.block_id
                    ),
                    0,
                )
                window_start = max(0, position - 2)
                window_end = min(len(scene_blocks), position + 7)
                window = scene_blocks[window_start:window_end]
                block = next(block for block in blocks if block.id == mention.block_id)
                candidates = detect_term_explanations(
                    term_mention_id=mention.id,
                    term_label=term.canonical_label,
                    mention_block_id=mention.block_id,
                    mention_start_in_block=mention.start_cp - block.start_cp,
                    mention_end_in_block=mention.end_cp - block.start_cp,
                    blocks=window,
                    client=cast(ModelClient, self._analysis_client),
                    warnings=explanation_warnings,
                )
                if not candidates and window_end < len(scene_blocks):
                    candidates = detect_term_explanations(
                        term_mention_id=mention.id,
                        term_label=term.canonical_label,
                        mention_block_id=mention.block_id,
                        mention_start_in_block=mention.start_cp - block.start_cp,
                        mention_end_in_block=mention.end_cp - block.start_cp,
                        blocks=scene_blocks[window_start:],
                        client=cast(ModelClient, self._analysis_client),
                        warnings=explanation_warnings,
                    )
                if candidates:
                    selected = min(
                        candidates,
                        key=lambda candidate: (
                            -int(candidate.completeness == "sufficient"),
                            -candidate.confidence,
                            abs(
                                self._block_start(blocks, candidate.block_id)
                                + candidate.start_in_block
                                - mention.start_cp
                            ),
                            self._block_start(blocks, candidate.block_id)
                            + candidate.start_in_block,
                            self._block_start(blocks, candidate.block_id)
                            + candidate.end_in_block,
                        ),
                    )
                    self.semantic.insert_raw(
                        annotation_type="term_explanation",
                        subject_type="term_mention",
                        subject_id=mention.id,
                        value={
                            "block_id": selected.block_id,
                            "explanation_kind": selected.explanation_kind,
                            "completeness": selected.completeness,
                        },
                        confidence=selected.confidence,
                        analysis_run_id=run_id,
                        start_cp=self._block_start(blocks, selected.block_id)
                        + selected.start_in_block,
                        end_cp=self._block_start(blocks, selected.block_id)
                        + selected.end_in_block,
                    )
            self._finish(
                run_id,
                status="partial" if explanation_warnings else "succeeded",
                warnings=explanation_warnings,
            )
        except AnalysisCancelledError as exc:
            self._finish(run_id, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return int(run_id)

    def _scene_semantics(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        scenes: Sequence[SceneRecord],
        blocks: Sequence[ModelJsonObject],
    ) -> int:
        run_id = self._new_run(
            "scene-semantic-classifier",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            config={"scene_taxonomy_version": 1},
        )
        try:
            if self._is_reused(run_id):
                return int(run_id)
            for scene in scenes:
                self._safe_point()
                result = classify_scene(
                    scene_id=scene.id,
                    blocks=[
                        block for block in blocks if block.get("scene_id") == scene.id
                    ],
                    client=cast(ModelClient, self._analysis_client),
                )
                for axis in ("function", "tone"):
                    values = result[axis]
                    assert isinstance(values, list)
                    self.semantic.insert_raw(
                        annotation_type=f"scene.{axis}",
                        subject_type="scene",
                        subject_id=scene.id,
                        value={"labels": values},
                        confidence=max(
                            validate_confidence(item["confidence"])
                            for item in values
                            if isinstance(item, dict)
                        ),
                        analysis_run_id=run_id,
                    )
                for axis in ("pace", "information_load", "interaction"):
                    value = result[axis]
                    assert isinstance(value, dict)
                    self.semantic.insert_raw(
                        annotation_type=f"scene.{axis}",
                        subject_type="scene",
                        subject_id=scene.id,
                        value=value,
                        confidence=validate_confidence(value["confidence"]),
                        analysis_run_id=run_id,
                    )
            self._finish(run_id)
        except AnalysisCancelledError as exc:
            self._finish(run_id, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return int(run_id)

    def _block_semantics(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        blocks: Sequence[BlockRecord],
        block_json: Sequence[ModelJsonObject],
    ) -> int:
        run_id = self._new_run(
            "block-semantic-classifier",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            config={"block_semantic_taxonomy_version": 1},
        )
        try:
            if self._is_reused(run_id):
                return int(run_id)
            self._safe_point()
            for block_id, value in classify_narration_blocks(
                blocks=list(block_json), client=cast(ModelClient, self._analysis_client)
            ):
                self.semantic.insert_raw(
                    annotation_type="block.semantic_primary",
                    subject_type="block",
                    subject_id=block_id,
                    value=value,
                    confidence=validate_confidence(value["confidence"]),
                    analysis_run_id=run_id,
                )
            self._finish(run_id)
        except AnalysisCancelledError as exc:
            self._finish(run_id, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return int(run_id)
