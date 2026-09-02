from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from novel_core.errors import AnalysisCancelledError
from novel_core.style_analysis.analyzers.entity_mentions import extract_entity_mentions
from novel_core.style_analysis.analyzers.entity_resolution import resolve_entity_mention
from novel_core.style_analysis.analyzers.pov_classifier import classify_pov
from novel_core.style_analysis.analyzers.speaker_attribution import attribute_speaker
from novel_core.style_analysis.analyzers.term_candidates import extract_term_candidates
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.model_contracts import ModelClient, validate_confidence
from novel_core.style_analysis.resolver_candidates import build_identity_shortlist
from novel_core.style_analysis.structure_models import BlockRecord, SceneRecord


def _alias_kind(mention_type: str) -> str:
    return {
        "proper_name": "name",
        "alias": "nickname",
        "role_title": "role",
        "pronoun": "pronoun",
    }.get(mention_type, "name")


class SemanticAnalysisMixin:
    def _semantic_analyzers(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        scenes: Sequence[SceneRecord],
        blocks: Sequence[BlockRecord],
    ) -> list[int]:
        revision = self.text.get_text_revision(document_id, text_revision_id)
        all_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        result: list[int] = []
        mention_run = self._new_run(
            "entity-mention-extractor",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
        )
        try:
            mention_warnings: list[str] = []
            if not self._is_reused(mention_run):
                for scene in scenes:
                    self._safe_point()
                    current = [
                        block for block in all_json if block.get("scene_id") == scene.id
                    ]
                    current_order = current[0].get("order_index", 0) if current else 0
                    if not isinstance(current_order, int):
                        current_order = 0
                    previous_scene = [
                        block
                        for block in all_json
                        if isinstance(block.get("order_index"), int)
                        and cast(int, block["order_index"]) < current_order
                        and block.get("scene_id") is not None
                    ][-3:]
                    mention_extracted = extract_entity_mentions(
                        scene_id=scene.id,
                        blocks=current,
                        previous_context_blocks=previous_scene,
                        client=cast(ModelClient, self._analysis_client),
                    )
                    mention_warnings.extend(mention_extracted.warnings)
                    for item in mention_extracted.items:
                        self.entities.repository.insert_mention(
                            structure_revision_id=structure_id,
                            scene_id=scene.id,
                            block_id=item.block_id,
                            start_cp=item.start_in_block
                            + self._block_start(blocks, item.block_id),
                            end_cp=item.end_in_block
                            + self._block_start(blocks, item.block_id),
                            surface=item.surface,
                            mention_type=item.mention_type,
                            entity_type_candidate=item.entity_type_candidate,
                            canonical_name_candidate=item.canonical_name_candidate,
                            confidence=item.confidence,
                            analysis_run_id=mention_run,
                        )
                self._finish(
                    mention_run,
                    status="partial" if mention_warnings else "succeeded",
                    warnings=mention_warnings,
                )
        except AnalysisCancelledError as exc:
            self._finish(mention_run, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(mention_run, status="failed", error=exc)
        result.append(mention_run)
        mention_failed = self.runs.get_run(mention_run)
        if mention_failed is not None and mention_failed.status == "failed":
            resolution_run = self._skip_dependent_run(
                "entity-resolver",
                document_id=document_id,
                text_revision_id=text_revision_id,
                structure_id=structure_id,
                dependency=mention_run,
            )
        else:
            resolution_run = self._resolve_entities(
                document_id, text_revision_id, structure_id, blocks, mention_run
            )
        result.append(resolution_run)
        resolution_failed = self.runs.get_run(resolution_run)
        if resolution_failed is not None and resolution_failed.status == "failed":
            speaker_run = self._skip_dependent_run(
                "speaker-attribution",
                document_id=document_id,
                text_revision_id=text_revision_id,
                structure_id=structure_id,
                dependency=resolution_run,
            )
            pov_run = self._skip_dependent_run(
                "pov-classifier",
                document_id=document_id,
                text_revision_id=text_revision_id,
                structure_id=structure_id,
                dependency=resolution_run,
            )
        else:
            speaker_run = self._speakers(
                document_id, text_revision_id, structure_id, blocks, resolution_run
            )
            pov_run = self._pov(
                document_id,
                text_revision_id,
                structure_id,
                scenes,
                blocks,
                resolution_run,
            )
        result.append(speaker_run)
        result.append(pov_run)
        term_candidate_run = self._new_run(
            "term-candidate-extractor",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
        )
        try:
            if not self._is_reused(term_candidate_run):
                term_warnings: list[str] = []
                for scene in scenes:
                    self._safe_point()
                    current = [
                        block for block in all_json if block.get("scene_id") == scene.id
                    ]
                    term_extracted = extract_term_candidates(
                        scene_id=scene.id,
                        blocks=current,
                        client=cast(ModelClient, self._analysis_client),
                    )
                    term_warnings.extend(term_extracted.warnings)
                    for term_item in term_extracted.items:
                        start = self._block_start(blocks, term_item.block_id)
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
                            analysis_run_id=term_candidate_run,
                            start_cp=start + term_item.start_in_block,
                            end_cp=start + term_item.end_in_block,
                        )
                self._finish(
                    term_candidate_run,
                    status="partial" if term_warnings else "succeeded",
                    warnings=term_warnings,
                )
        except AnalysisCancelledError as exc:
            self._finish(term_candidate_run, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(term_candidate_run, status="failed", error=exc)
        result.append(term_candidate_run)
        term_failed = self.runs.get_run(term_candidate_run)
        if term_failed is not None and term_failed.status == "failed":
            term_resolution_run = self._skip_dependent_run(
                "term-resolver",
                document_id=document_id,
                text_revision_id=text_revision_id,
                structure_id=structure_id,
                dependency=term_candidate_run,
            )
        else:
            term_resolution_run = self._resolve_terms(
                document_id, text_revision_id, structure_id, blocks, term_candidate_run
            )
        result.append(term_resolution_run)
        term_resolution_failed = self.runs.get_run(term_resolution_run)
        if (
            term_resolution_failed is not None
            and term_resolution_failed.status == "failed"
        ):
            explanation_run = self._skip_dependent_run(
                "term-explanation-detector",
                document_id=document_id,
                text_revision_id=text_revision_id,
                structure_id=structure_id,
                dependency=term_resolution_run,
            )
        else:
            explanation_run = self._explanations(
                document_id, text_revision_id, structure_id, blocks, term_resolution_run
            )
        result.append(explanation_run)
        scene_run = self._scene_semantics(
            document_id, text_revision_id, structure_id, scenes, all_json
        )
        result.append(scene_run)
        block_run = self._block_semantics(
            document_id, text_revision_id, structure_id, blocks, all_json
        )
        result.append(block_run)
        return result

    def _skip_dependent_run(
        self: Any,
        analyzer_id: str,
        *,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        dependency: int,
    ) -> int:
        run_id = self._new_run(
            analyzer_id,
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            dependencies=(dependency,),
            reuse=False,
        )
        self._finish(
            run_id,
            status="failed",
            error=ValueError("DEPENDENCY_FAILED"),
        )
        return int(run_id)

    def _resolve_entities(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        blocks: Sequence[BlockRecord],
        mention_run: int,
    ) -> int:
        scope = self.entities._scope(document_id)
        registry = self.entities.candidate_rows(
            document_id=document_id,
            entity_type="other",
            surface="",
            same_scene_ids=set(),
        )
        run_id = self._new_run(
            "entity-resolver",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            dependencies=(mention_run,),
            state_fingerprint=fingerprint_json(
                cast(
                    JsonValue,
                    {
                        "scope": scope,
                        "entity_registry_state": self._entity_registry_state(
                            document_id
                        ),
                    },
                )
            ),
            policy_inputs=("entity_resolution_auto_merge",),
            registry_input_fingerprint=fingerprint_json(cast(JsonValue, registry)),
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        block_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        try:
            if self._is_reused(run_id):
                return int(run_id)
            resolved_by_scene: dict[int, set[int]] = {}
            for mention in self.entities.repository.list_mentions(
                analysis_run_id=mention_run
            ):
                self._safe_point()
                exact = self.entities.exact_matches(
                    document_id=document_id, surface=mention.surface
                )
                if len(exact) == 1:
                    decision_id = exact[0].id
                    resolved_by_scene.setdefault(mention.scene_id, set()).add(
                        decision_id
                    )
                    self.semantic.insert_raw(
                        annotation_type="mention.entity_resolution",
                        subject_type="mention",
                        subject_id=mention.id,
                        value={"entity_id": decision_id},
                        confidence=1.0,
                        analysis_run_id=run_id,
                    )
                    continue
                if len(exact) > 1:
                    continue
                previous, subject, following = self._context(
                    block_json, mention.block_id, 2, 2
                )
                candidates = self.entities.candidate_rows(
                    document_id=document_id,
                    entity_type=mention.entity_type_candidate,
                    surface=mention.surface,
                    same_scene_ids=resolved_by_scene.get(mention.scene_id, set()),
                )
                candidates = build_identity_shortlist(
                    surface=mention.surface,
                    canonical_name=mention.canonical_name_candidate,
                    candidate_type=mention.entity_type_candidate,
                    identities=candidates,
                    same_scene_ids=resolved_by_scene.get(mention.scene_id, set()),
                )
                if mention.mention_type in {"pronoun", "role_title"}:
                    candidates = [
                        candidate
                        for candidate in candidates
                        if candidate.get("same_scene") is True
                    ]
                decision = resolve_entity_mention(
                    mention={
                        "mention_id": mention.id,
                        "surface": mention.surface,
                        "mention_type": mention.mention_type,
                        "entity_type_candidate": mention.entity_type_candidate,
                        "canonical_name_candidate": mention.canonical_name_candidate,
                    },
                    previous_blocks=previous,
                    subject_block=subject,
                    next_blocks=following,
                    candidates=candidates,
                    auto_merge_threshold=self.policy.entity_resolution_auto_merge,
                    client=cast(ModelClient, self._analysis_client),
                )
                if decision.decision == "existing" and decision.entity_id is not None:
                    entity = self.entities.repository.get(decision.entity_id)
                    self.semantic.insert_raw(
                        annotation_type="mention.entity_resolution",
                        subject_type="mention",
                        subject_id=mention.id,
                        value={"entity_id": decision.entity_id},
                        confidence=decision.confidence,
                        analysis_run_id=run_id,
                    )
                    resolved_by_scene.setdefault(mention.scene_id, set()).add(entity.id)
                    self.entities.insert_inferred_alias_if_missing(
                        entity_id=entity.id,
                        alias=mention.surface,
                        alias_kind=_alias_kind(mention.mention_type),
                        analysis_run_id=run_id,
                        source_mention_id=mention.id,
                    )
                elif (
                    decision.decision == "new"
                    and decision.new_entity_type
                    and decision.new_canonical_name
                ):
                    scope = self.entities._scope(document_id)
                    entity = self.entities.repository.create_inferred(
                        reference_work_id=scope.get("reference_work_id"),
                        document_id=scope.get("document_id"),
                        entity_type=decision.new_entity_type,
                        canonical_name=decision.new_canonical_name,
                        run_id=run_id,
                    )
                    self.semantic.insert_raw(
                        annotation_type="mention.entity_resolution",
                        subject_type="mention",
                        subject_id=mention.id,
                        value={"entity_id": entity.id},
                        confidence=decision.confidence,
                        analysis_run_id=run_id,
                    )
                    resolved_by_scene.setdefault(mention.scene_id, set()).add(entity.id)
            self._finish(run_id)
        except AnalysisCancelledError as exc:
            self._finish(run_id, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return int(run_id)

    def _speakers(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        blocks: Sequence[BlockRecord],
        dependency: int,
    ) -> int:
        run_id = self._new_run(
            "speaker-attribution",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            dependencies=(dependency,),
            state_fingerprint=fingerprint_json(
                cast(
                    JsonValue,
                    {
                        "mention_resolution": self._mention_resolution_state(
                            document_id, structure_id, dependency
                        )
                    },
                )
            ),
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        block_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        try:
            if self._is_reused(run_id):
                return int(run_id)
            for block in blocks:
                if block.block_type != "dialogue":
                    continue
                self._safe_point()
                people = self._people_for_scene(document_id, dependency, block.scene_id)
                previous, subject, following = self._context(block_json, block.id, 4, 4)
                value = attribute_speaker(
                    previous_blocks=previous,
                    subject_block=subject,
                    next_blocks=following,
                    people=people,
                    client=cast(ModelClient, self._analysis_client),
                )
                self.semantic.insert_raw(
                    annotation_type="speaker",
                    subject_type="block",
                    subject_id=block.id,
                    value={
                        "speaker_entity_id": value.speaker_entity_id,
                        "evidence_block_ids": list(value.evidence_block_ids),
                        "reason_code": value.reason_code,
                    },
                    confidence=value.confidence,
                    analysis_run_id=run_id,
                )
            self._finish(run_id)
        except AnalysisCancelledError as exc:
            self._finish(run_id, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return int(run_id)

    def _pov(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        scenes: Sequence[SceneRecord],
        blocks: Sequence[BlockRecord],
        dependency: int,
    ) -> int:
        run_id = self._new_run(
            "pov-classifier",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            dependencies=(dependency,),
            state_fingerprint=fingerprint_json(
                cast(
                    JsonValue,
                    {
                        "mention_resolution": self._mention_resolution_state(
                            document_id, structure_id, dependency
                        )
                    },
                )
            ),
            config={"pov_taxonomy_version": 1},
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        try:
            if self._is_reused(run_id):
                return int(run_id)
            for scene in scenes:
                self._safe_point()
                scene_json = [
                    self._block_json(block, revision.canonical_text)
                    for block in blocks
                    if block.scene_id == scene.id
                ]
                people = self._people_for_scene(document_id, dependency, scene.id)
                value = classify_pov(
                    scene_id=scene.id,
                    blocks=scene_json,
                    people=people,
                    client=cast(ModelClient, self._analysis_client),
                )
                self.semantic.insert_raw(
                    annotation_type="scene.pov",
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
