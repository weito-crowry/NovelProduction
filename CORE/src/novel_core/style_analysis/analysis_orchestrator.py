from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from novel_core.errors import AnalysisCancelledError
from novel_core.style_analysis.aggregate_repository import MeasurementRepository
from novel_core.style_analysis.analysis_orchestrator_basic import BasicMetricsMixin
from novel_core.style_analysis.analysis_orchestrator_metrics import (
    SemanticMetricsMixin,
)
from novel_core.style_analysis.analysis_orchestrator_semantic import (
    SemanticAnalysisMixin,
)
from novel_core.style_analysis.analysis_orchestrator_state import AnalysisStateMixin
from novel_core.style_analysis.analysis_orchestrator_terms import (
    TermAndSceneAnalysisMixin,
)
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.analysis_runtime import (
    AnalysisRuntime,
    execution_fingerprint,
)
from novel_core.style_analysis.analyzers.scene_boundary import detect_scene_boundaries
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.fingerprints import (
    JsonObject as StoredJsonObject,
)
from novel_core.style_analysis.fingerprints import (
    JsonValue,
    fingerprint_json,
)
from novel_core.style_analysis.model_contracts import (
    JsonObject as ModelJsonObject,
)
from novel_core.style_analysis.model_contracts import (
    ModelClient,
    ModelRequest,
)
from novel_core.style_analysis.model_output_contracts import ResponseContractRegistry
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.resumable_engine import ResumableDocumentAnalysisEngine
from novel_core.style_analysis.resumable_models import (
    CompletedModelCall,
    DocumentAnalysisRequest,
)
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


def reduce_term_novelty(values: Sequence[str]) -> str:
    concrete = {value for value in values if value != "uncertain"}
    return next(iter(concrete)) if len(concrete) == 1 else "uncertain"


class _SafePointModelClient:
    def __init__(self, delegate: ModelClient, safe_point: Callable[[], None]) -> None:
        self._delegate = delegate
        self._safe_point = safe_point

    def complete_json(self, request: ModelRequest) -> ModelJsonObject:
        self._safe_point()
        try:
            return self._delegate.complete_json(request)
        finally:
            self._safe_point()

    def complete_json_validated(
        self,
        request: ModelRequest,
        validator: Callable[[ModelJsonObject], ModelJsonObject],
    ) -> ModelJsonObject:
        self._safe_point()
        try:
            validated = getattr(self._delegate, "complete_json_validated", None)
            if callable(validated):
                return cast(ModelJsonObject, validated(request, validator))
            return validator(self._delegate.complete_json(request))
        finally:
            self._safe_point()


class DocumentAnalysisOrchestrator(
    SemanticAnalysisMixin,
    SemanticMetricsMixin,
    TermAndSceneAnalysisMixin,
    AnalysisStateMixin,
    BasicMetricsMixin,
):
    def __init__(
        self,
        connection: object,
        *,
        model_client: ModelClient | None,
        model_provider: str | None = None,
        model_id: str | None = None,
        policy: AnalysisPolicy | None = None,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> None:
        import sqlite3

        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("sqlite connection required")
        self.connection = connection
        self.client = model_client
        self.model_provider = model_provider
        self.model_id = model_id
        self.policy = policy or AnalysisPolicy()
        self._cancellation_probe = cancellation_probe
        self._analysis_client = (
            _SafePointModelClient(model_client, self._safe_point)
            if model_client is not None
            else None
        )
        self.runs = AnalysisRunRepository(connection)
        self.runtime = AnalysisRuntime(self.runs)
        self._reused_run_ids: set[int] = set()
        self.structure = StyleStructureService(connection)
        self.text = StyleTextService(connection)
        self.entities = EntityService(connection)
        self.terms = TermService(connection)
        self.semantic = SemanticService(connection)
        self.measurements = MeasurementRepository(connection)

    def analyze_document(
        self,
        *,
        document_id: int,
        text_revision_id: int | None = None,
        structure_revision_id: int | None = None,
        preset: str = "full",
        rebuild_structure: bool = False,
    ) -> DocumentAnalysisResult:
        return self._analyze_resumable(
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            preset=preset,
            rebuild_structure=rebuild_structure,
        )

    def _analyze_resumable(
        self,
        *,
        document_id: int,
        text_revision_id: int | None,
        structure_revision_id: int | None,
        preset: str,
        rebuild_structure: bool,
    ) -> DocumentAnalysisResult:
        if preset not in {"deterministic", "full", "metrics"}:
            raise ValueError("ANALYSIS_PRESET_INVALID")
        if text_revision_id is None:
            raise ValueError("TEXT_REVISION_REQUIRED")
        if preset == "metrics" and structure_revision_id is None:
            raise ValueError("STRUCTURE_REVISION_REQUIRED")
        if preset == "full" and self.client is None:
            raise ValueError("ANALYZER_PROVIDER_UNAVAILABLE")
        engine = ResumableDocumentAnalysisEngine(
            self.connection,
            model_provider=self.model_provider or "internal",
            model_id=self.model_id or "internal",
            policy=self.policy,
            checkpoint=self._safe_point,
        )
        request = DocumentAnalysisRequest(
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            preset=preset,
            rebuild_structure=rebuild_structure,
        )
        cursor: ModelJsonObject = {"schema_version": 1}
        completed: CompletedModelCall | None = None
        while True:
            advanced = engine.advance(request, cursor, completed)
            cursor = advanced.cursor
            if advanced.result is not None:
                return advanced.result
            call = advanced.pending_call
            if call is None or self._analysis_client is None:
                raise ValueError("ANALYZER_PROVIDER_UNAVAILABLE")
            model_request = ModelRequest(
                prompt_id=call.prompt_id,
                prompt_version=call.prompt_version,
                system_prompt=call.system_prompt,
                user_payload=call.user_payload,
            )
            try:
                response = self._analysis_client.complete_json_validated(
                    model_request,
                    ResponseContractRegistry.get(call.response_contract_id).validator,
                )
                completed = CompletedModelCall(
                    call_key=call.call_key, response=response
                )
            except Exception as exc:
                completed = CompletedModelCall(
                    call_key=call.call_key,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )

    def _safe_point(self) -> None:
        self.runs.commit()
        if self._cancellation_probe is not None and self._cancellation_probe():
            raise AnalysisCancelledError()

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
        config: JsonValue | None = None,
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
        model_provider = self.model_provider if prompt_id is not None else None
        model_id = self.model_id if prompt_id is not None else None
        config_json = _json(config if config is not None else {})
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
            existing = (
                self.runtime.resolve_cache_hit(
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
                    model_provider=model_provider,
                    model_id=model_id,
                )
                if definition.cacheable
                else None
            )
            if existing is not None:
                self._reused_run_ids.add(existing.id)
                return existing.id
        fingerprint = execution_fingerprint(
            analyzer_id=analyzer_id,
            analyzer_version=definition.version,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_revision_id,
            config=config if config is not None else {},
            state_fingerprint=state_fingerprint,
            policy_input_fingerprint=policy_input_fingerprint,
            dependency_runs=dependency_pairs,
            model_provider=model_provider,
            model_id=model_id,
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
            model_provider=model_provider,
            model_id=model_id,
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
                self._safe_point()
                candidates = detect_scene_boundaries(
                    base_structure_revision_id=structure_id,
                    scene_id=scene.id,
                    blocks=scene_blocks,
                    client=cast(ModelClient, self._analysis_client),
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
            self._finish(run_id)
        except AnalysisCancelledError as exc:
            self._finish(run_id, status="cancelled", error=exc)
            raise
        except Exception as exc:
            self._finish(run_id, status="failed", error=exc)
            raise
        return run_id

    def _skip_dependent_run(
        self,
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
        return run_id


def _alias_kind(mention_type: str) -> str:
    return {
        "proper_name": "name",
        "alias": "nickname",
        "role_title": "role",
        "pronoun": "pronoun",
    }.get(mention_type, "name")
