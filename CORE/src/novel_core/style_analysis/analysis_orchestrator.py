from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.analysis_runtime import (
    AnalysisRuntime,
    execution_fingerprint,
)
from novel_core.style_analysis.analyzers.block_semantics import (
    classify_narration_blocks,
)
from novel_core.style_analysis.analyzers.entity_mentions import extract_entity_mentions
from novel_core.style_analysis.analyzers.entity_resolution import resolve_entity_mention
from novel_core.style_analysis.analyzers.pov_classifier import classify_pov
from novel_core.style_analysis.analyzers.scene_boundary import detect_scene_boundaries
from novel_core.style_analysis.analyzers.scene_classifier import classify_scene
from novel_core.style_analysis.analyzers.speaker_attribution import attribute_speaker
from novel_core.style_analysis.analyzers.term_candidates import extract_term_candidates
from novel_core.style_analysis.analyzers.term_explanation import (
    detect_term_explanations,
)
from novel_core.style_analysis.analyzers.term_resolution import resolve_term_candidate
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.fingerprints import (
    JsonObject as StoredJsonObject,
)
from novel_core.style_analysis.fingerprints import (
    JsonValue,
    fingerprint_json,
)
from novel_core.style_analysis.metrics import calculate_basic_metrics
from novel_core.style_analysis.model_contracts import (
    JsonObject as ModelJsonObject,
)
from novel_core.style_analysis.model_contracts import (
    ModelClient,
    validate_confidence,
)
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.runtime_models import (
    AnalysisPolicy,
    DependencyRunExpectation,
    RunStatus,
)
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID
from novel_core.style_analysis.semantic_service import SemanticService
from novel_core.style_analysis.structure_models import (
    BlockRecord,
    SceneRecord,
    SentenceRecord,
)
from novel_core.style_analysis.structure_service import StyleStructureService
from novel_core.style_analysis.term_service import TermService
from novel_core.style_analysis.text_service import StyleTextService


@dataclass(frozen=True, slots=True)
class DocumentAnalysisResult:
    status: str
    text_revision_id: int
    structure_revision_id: int
    run_ids: tuple[int, ...]
    warnings: tuple[str, ...]
    metrics: tuple[StoredJsonObject, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class DocumentAnalysisOrchestrator:
    def __init__(
        self,
        connection: object,
        *,
        model_client: ModelClient | None,
        model_provider: str | None = None,
        model_id: str | None = None,
        policy: AnalysisPolicy | None = None,
    ) -> None:
        import sqlite3

        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("sqlite connection required")
        self.connection = connection
        self.client = model_client
        self.model_provider = model_provider
        self.model_id = model_id
        self.policy = policy or AnalysisPolicy()
        self.runs = AnalysisRunRepository(connection)
        self.runtime = AnalysisRuntime(self.runs)
        self._reused_run_ids: set[int] = set()
        self.structure = StyleStructureService(connection)
        self.text = StyleTextService(connection)
        self.entities = EntityService(connection)
        self.terms = TermService(connection)
        self.semantic = SemanticService(connection)

    def analyze_document(
        self,
        *,
        document_id: int,
        text_revision_id: int | None = None,
        structure_revision_id: int | None = None,
        preset: str = "full",
        rebuild_structure: bool = False,
    ) -> DocumentAnalysisResult:
        if preset not in {"deterministic", "full"}:
            raise ValueError("ANALYSIS_PRESET_INVALID")
        document = self.text.get_document(document_id)
        if document is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        revision_id = text_revision_id or document.current_text_revision_id
        if revision_id is None:
            raise ValueError("TEXT_REVISION_REQUIRED")
        revision = self.text.get_text_revision(document_id, revision_id)
        final_structure_id = structure_revision_id
        if final_structure_id is None and not rebuild_structure:
            final_structure_id = document.current_structure_revision_id
        if final_structure_id is None:
            final_structure_id = self.structure.build_automatic_structure(
                document_id=document_id, text_revision_id=revision.id
            ).id
        structure = self.structure.get_structure_revision(
            document_id, final_structure_id
        )
        if structure.text_revision_id != revision.id:
            raise ValueError("STRUCTURE_TEXT_REVISION_MISMATCH")
        scenes = self.structure.list_scenes(structure.id)
        blocks = self.structure.list_blocks(structure.id)
        sentences = self.structure.list_sentences(structure.id)
        run_ids: list[int] = []
        warnings: list[str] = []
        metrics: list[StoredJsonObject] = []
        if preset == "full" and self.client is None:
            raise ValueError("ANALYZER_PROVIDER_UNAVAILABLE")

        if (
            preset == "full"
            and structure.source_kind == "automatic"
            and structure_revision_id is None
        ):
            try:
                run_id = self._boundary(
                    document_id, revision.id, structure.id, scenes, blocks
                )
                run_ids.append(run_id)
            except Exception as exc:
                warnings.append(f"BOUNDARY_FAILED:{exc}")

        if preset == "full":
            try:
                run_ids.extend(
                    self._semantic_analyzers(
                        document_id, revision.id, structure.id, scenes, blocks
                    )
                )
            except Exception as exc:
                warnings.append(f"SEMANTIC_FAILED:{exc}")
        try:
            basic_run, basic_metrics = self._basic(
                document_id,
                revision.id,
                structure.id,
                revision.canonical_text,
                scenes,
                blocks,
                sentences,
            )
            run_ids.append(basic_run)
            metrics.extend(basic_metrics)
        except Exception:
            raise
        for run_id in run_ids:
            run = self.runs.get_run(run_id)
            if run is not None and run.status != "succeeded":
                warnings.append(f"ANALYZER_{run.status.upper()}:{run.analyzer_id}")
        self.runs.commit()
        return DocumentAnalysisResult(
            status="partial" if warnings else "succeeded",
            text_revision_id=revision.id,
            structure_revision_id=structure.id,
            run_ids=tuple(run_ids),
            warnings=tuple(warnings),
            metrics=tuple(metrics),
        )

    def _new_run(
        self,
        analyzer_id: str,
        *,
        document_id: int,
        text_revision_id: int,
        structure_revision_id: int,
        dependencies: Sequence[int] = (),
        state_fingerprint: str | None = None,
        policy_inputs: tuple[str, ...] = (),
        registry_input_fingerprint: str | None = None,
        reuse: bool = True,
    ) -> int:
        definition = ANALYZERS_BY_ID[analyzer_id]
        prompt_id = None
        prompt_version = None
        prompt_map = {
            "scene-boundary-detector": "style.scene_boundary",
            "entity-mention-extractor": "style.entity_mentions",
            "entity-resolver": "style.entity_resolution",
            "speaker-attribution": "style.speaker_attribution",
            "term-candidate-extractor": "style.term_candidates",
            "term-resolver": "style.term_resolution",
            "term-explanation-detector": "style.term_explanation",
            "scene-semantic-classifier": "style.scene_semantics",
            "block-semantic-classifier": "style.block_semantic",
            "pov-classifier": "style.pov",
        }
        if analyzer_id in prompt_map:
            prompt = get_prompt(prompt_map[analyzer_id])
            prompt_id, prompt_version = prompt.prompt_id, prompt.version
        config_json = _json({})
        dependency_pairs_list: list[tuple[str, int]] = []
        for run_id in dependencies:
            dependency = self.runs.get_run(run_id)
            if dependency is not None:
                dependency_pairs_list.append((dependency.analyzer_id, run_id))
        dependency_pairs = tuple(dependency_pairs_list)
        policy_input_fingerprint = (
            fingerprint_json(cast(JsonValue, self.policy.input_values(policy_inputs)))
            if policy_inputs
            else None
        )
        if reuse:
            expectation_list: list[DependencyRunExpectation] = []
            for dependency_id, dependency_run_id in dependency_pairs:
                dependency = self.runs.get_run(dependency_run_id)
                if dependency is not None:
                    expectation_list.append(
                        DependencyRunExpectation(
                            analyzer_id=dependency_id,
                            run_id=dependency_run_id,
                            config_json=dependency.config_json,
                            state_fingerprint=dependency.state_fingerprint,
                            policy_input_fingerprint=dependency.policy_input_fingerprint,
                            prompt_id=dependency.prompt_id,
                            prompt_version=dependency.prompt_version,
                        )
                    )
            expectations = tuple(expectation_list)
            existing = self.runtime.resolve_current_run(
                document_id=document_id,
                analyzer_id=analyzer_id,
                text_revision_id=text_revision_id,
                structure_revision_id=structure_revision_id,
                analyzer_version=definition.version,
                config_json=config_json,
                state_fingerprint=state_fingerprint,
                policy_input_fingerprint=policy_input_fingerprint,
                dependency_runs=dependency_pairs,
                dependency_expectations=expectations,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                model_provider=self.model_provider,
                model_id=self.model_id,
            )
            if existing is not None:
                self._reused_run_ids.add(existing.id)
                return existing.id
        fingerprint = execution_fingerprint(
            analyzer_id=analyzer_id,
            analyzer_version=definition.version,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            config={},
            state_fingerprint=state_fingerprint,
            policy_input_fingerprint=policy_input_fingerprint,
            dependency_runs=dependency_pairs,
            model_provider=self.model_provider,
            model_id=self.model_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
        run_id = self.runs.insert_run(
            document_id=document_id,
            analyzer_id=analyzer_id,
            analyzer_version=definition.version,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            status="running",
            fingerprint=fingerprint,
            config_json=config_json,
            analysis_policy_version=self.policy.version,
            policy_input_fingerprint=policy_input_fingerprint,
            state_fingerprint=state_fingerprint,
            registry_input_fingerprint=registry_input_fingerprint,
            model_provider=self.model_provider,
            model_id=self.model_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            started_at=_now(),
        )
        for dependency_run_id in dependencies:
            self.runs.add_dependency(run_id, dependency_run_id)
        return run_id

    def _is_reused(self, run_id: int) -> bool:
        return run_id in self._reused_run_ids

    def _finish(
        self,
        run_id: int,
        *,
        status: str = "succeeded",
        warnings: Sequence[str] = (),
        error: Exception | None = None,
    ) -> None:
        self.runs.finish_run(
            run_id,
            status=cast(RunStatus, status),
            error_code=(str(error) if error else None),
            error_message=(str(error) if error else None),
            warning_json=_json(list(warnings)),
        )

    def _boundary(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        scenes: Sequence[SceneRecord],
        blocks: Sequence[BlockRecord],
    ) -> int:
        run_id = self._new_run(
            "scene-boundary-detector",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        try:
            if self._is_reused(run_id):
                return run_id
            for scene in scenes:
                scene_blocks = [
                    self._block_json(block, revision.canonical_text)
                    for block in blocks
                    if block.scene_id == scene.id
                ]
                if len(scene_blocks) < 2:
                    continue
                candidates = detect_scene_boundaries(
                    base_structure_revision_id=structure_id,
                    scene_id=scene.id,
                    blocks=scene_blocks,
                    client=cast(ModelClient, self.client),
                )
                for candidate in candidates:
                    self.semantic.insert_raw(
                        annotation_type="scene_boundary_candidate",
                        subject_type="scene",
                        subject_id=scene.id,
                        value={
                            "after_block_id": candidate.after_block_id,
                            "reasons": list(candidate.reasons),
                        },
                        confidence=candidate.confidence,
                        analysis_run_id=run_id,
                    )
            self._finish(run_id)
        except Exception as exc:
            self._finish(run_id, status="failed", error=exc)
            raise
        return run_id

    def _semantic_analyzers(
        self,
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
                        client=cast(ModelClient, self.client),
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
        except Exception as exc:
            self._finish(mention_run, status="failed", error=exc)
            raise
        result.append(mention_run)
        resolution_run = self._resolve_entities(
            document_id, text_revision_id, structure_id, blocks, mention_run
        )
        result.append(resolution_run)
        speaker_run = self._speakers(
            document_id, text_revision_id, structure_id, blocks, resolution_run
        )
        result.append(speaker_run)
        pov_run = self._pov(
            document_id, text_revision_id, structure_id, scenes, blocks, resolution_run
        )
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
                    current = [
                        block for block in all_json if block.get("scene_id") == scene.id
                    ]
                    term_extracted = extract_term_candidates(
                        scene_id=scene.id,
                        blocks=current,
                        client=cast(ModelClient, self.client),
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
        except Exception as exc:
            self._finish(term_candidate_run, status="failed", error=exc)
            raise
        result.append(term_candidate_run)
        term_resolution_run = self._resolve_terms(
            document_id, text_revision_id, structure_id, blocks, term_candidate_run
        )
        result.append(term_resolution_run)
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

    def _resolve_entities(
        self,
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
                cast(JsonValue, {"scope": scope, "registry": registry})
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
                return run_id
            for mention in self.entities.repository.list_mentions(
                analysis_run_id=mention_run
            ):
                exact = self.entities.exact_matches(
                    document_id=document_id, surface=mention.surface
                )
                decision = None
                if len(exact) == 1:
                    decision_id = exact[0].id
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
                    same_scene_ids=set(),
                )
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
                    client=cast(ModelClient, self.client),
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
                    if entity.canonical_name != mention.surface:
                        self.entities.repository.insert_alias(
                            entity_id=entity.id,
                            alias=mention.surface,
                            alias_kind=_alias_kind(mention.mention_type),
                            origin="inferred",
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
                    if decision.new_canonical_name != mention.surface:
                        self.entities.repository.insert_alias(
                            entity_id=entity.id,
                            alias=mention.surface,
                            alias_kind=_alias_kind(mention.mention_type),
                            origin="inferred",
                            analysis_run_id=run_id,
                            source_mention_id=mention.id,
                        )
            self._finish(run_id)
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return run_id

    def _speakers(
        self,
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
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        block_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        try:
            if self._is_reused(run_id):
                return run_id
            people = [
                {"entity_id": entity.id, "canonical_name": entity.canonical_name}
                for entity in self.entities.repository.list_for_scope(
                    **self.entities._scope(document_id)
                )
                if entity.entity_type == "person"
            ]
            for block in blocks:
                if block.block_type != "dialogue":
                    continue
                previous, subject, following = self._context(block_json, block.id, 4, 4)
                value = attribute_speaker(
                    previous_blocks=previous,
                    subject_block=subject,
                    next_blocks=following,
                    people=people,
                    client=cast(ModelClient, self.client),
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
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return run_id

    def _pov(
        self,
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
            state_fingerprint=fingerprint_json({"mention_resolution": dependency}),
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        try:
            if self._is_reused(run_id):
                return run_id
            people = [
                {"entity_id": entity.id, "canonical_name": entity.canonical_name}
                for entity in self.entities.repository.list_for_scope(
                    **self.entities._scope(document_id)
                )
                if entity.entity_type == "person"
            ]
            for scene in scenes:
                scene_json = [
                    self._block_json(block, revision.canonical_text)
                    for block in blocks
                    if block.scene_id == scene.id
                ]
                value = classify_pov(
                    scene_id=scene.id,
                    blocks=scene_json,
                    people=people,
                    client=cast(ModelClient, self.client),
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
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return run_id

    def _resolve_terms(
        self,
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
                cast(JsonValue, {"scope": scope, "registry": registry})
            ),
            policy_inputs=("term_resolution_auto_merge",),
            registry_input_fingerprint=fingerprint_json(
                cast(
                    JsonValue,
                    registry,
                )
            ),
        )
        revision = self.text.get_text_revision(document_id, text_revision_id)
        block_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        try:
            if self._is_reused(run_id):
                return run_id
            annotations = self.semantic.repository.list_for_run(candidate_run)
            for annotation in annotations:
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
                        same_scene_ids=set(),
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
                        client=cast(ModelClient, self.client),
                    )
                    if decision.decision == "unresolved":
                        continue
                    if decision.decision == "existing" and decision.term_id is not None:
                        term = self.terms.repository.get(decision.term_id)
                        term_id, confidence = decision.term_id, decision.confidence
                        if term.canonical_label != str(value["surface"]):
                            self.terms.repository.insert_alias(
                                term_id=term.id,
                                alias=str(value["surface"]),
                                origin="inferred",
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
                        if decision.new_canonical_label != str(value["surface"]):
                            self.terms.repository.insert_alias(
                                term_id=term.id,
                                alias=str(value["surface"]),
                                origin="inferred",
                                analysis_run_id=run_id,
                            )
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
                novelty = str(value.get("novelty_candidate", "uncertain"))
                self.semantic.insert_raw(
                    annotation_type="term.novelty",
                    subject_type="term",
                    subject_id=term_id,
                    value={"value": novelty},
                    confidence=confidence,
                    analysis_run_id=run_id,
                )
            self._finish(run_id)
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return run_id

    def _explanations(
        self,
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
        try:
            if self._is_reused(run_id):
                return run_id
            for mention in self.terms.repository.list_mentions(
                analysis_run_id=dependency
            ):
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
                window = scene_blocks[max(0, position - 2) : position + 7]
                block = next(block for block in blocks if block.id == mention.block_id)
                candidates = detect_term_explanations(
                    term_mention_id=mention.id,
                    term_label=term.canonical_label,
                    mention_block_id=mention.block_id,
                    mention_start_in_block=mention.start_cp - block.start_cp,
                    mention_end_in_block=mention.end_cp - block.start_cp,
                    blocks=window,
                    client=cast(ModelClient, self.client),
                )
                if candidates:
                    selected = candidates[0]
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
            self._finish(run_id)
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return run_id

    def _scene_semantics(
        self,
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
        )
        try:
            if self._is_reused(run_id):
                return run_id
            for scene in scenes:
                result = classify_scene(
                    scene_id=scene.id,
                    blocks=[
                        block for block in blocks if block.get("scene_id") == scene.id
                    ],
                    client=cast(ModelClient, self.client),
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
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return run_id

    def _block_semantics(
        self,
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
        )
        try:
            if self._is_reused(run_id):
                return run_id
            for block_id, value in classify_narration_blocks(
                blocks=list(block_json), client=cast(ModelClient, self.client)
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
        except Exception as exc:
            self._finish(run_id, status="partial", error=exc)
        return run_id

    def _basic(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        text: str,
        scenes: Sequence[SceneRecord],
        blocks: Sequence[BlockRecord],
        sentences: Sequence[SentenceRecord],
    ) -> tuple[int, list[StoredJsonObject]]:
        run_id = self._new_run(
            "style-metrics-basic",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            reuse=False,
        )
        try:
            measurements = calculate_basic_metrics(
                document_id=document_id,
                canonical_text=text,
                scenes=tuple(scenes),
                blocks=tuple(blocks),
                sentences=tuple(sentences),
            )
            values: list[StoredJsonObject] = [
                {
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "metric_name": item.metric_name,
                    "metric_version": item.metric_version,
                    "value": item.value,
                    "sample_count": item.sample_count,
                }
                for item in measurements
            ]
            self._finish(run_id)
            return run_id, values
        except Exception as exc:
            self._finish(run_id, status="failed", error=exc)
            raise

    @staticmethod
    def _block_json(block: BlockRecord, text: str) -> ModelJsonObject:
        return {
            "block_id": block.id,
            "scene_id": block.scene_id,
            "order_index": block.order_index,
            "block_type": block.block_type,
            "text": text[block.start_cp : block.end_cp],
        }

    @staticmethod
    def _block_start(blocks: Sequence[BlockRecord], block_id: int) -> int:
        for block in blocks:
            if block.id == block_id:
                return block.start_cp
        raise ValueError("BLOCK_NOT_FOUND")

    @staticmethod
    def _block_scene(blocks: Sequence[BlockRecord], block_id: int) -> int:
        for block in blocks:
            if block.id == block_id and block.scene_id is not None:
                return block.scene_id
        raise ValueError("SCENE_NOT_FOUND")

    @staticmethod
    def _context(
        blocks: Sequence[ModelJsonObject], block_id: int, before: int, after: int
    ) -> tuple[list[ModelJsonObject], ModelJsonObject, list[ModelJsonObject]]:
        from novel_core.style_analysis.resolver_candidates import build_context_window

        return build_context_window(
            blocks, subject_block_id=block_id, before=before, after=after
        )


def _alias_kind(mention_type: str) -> str:
    return {
        "proper_name": "name",
        "alias": "nickname",
        "role_title": "role",
        "pronoun": "title",
    }.get(mention_type, "name")
