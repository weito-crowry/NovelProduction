from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast

from novel_core.style_analysis.aggregate_repository import MeasurementRepository
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.analysis_runtime import (
    AnalysisRuntime,
    execution_fingerprint,
)
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.entity_service import EntityService
from novel_core.style_analysis.fingerprints import (
    JsonObject as StoredJsonObject,
)
from novel_core.style_analysis.fingerprints import (
    JsonValue,
    canonical_json_bytes,
)
from novel_core.style_analysis.metrics import (
    BASIC_METRIC_DEFINITIONS,
    SEMANTIC_METRIC_DEFINITIONS,
)
from novel_core.style_analysis.model_contracts import JsonObject
from novel_core.style_analysis.model_output_contracts import ResponseContractRegistry
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.resumable_models import (
    CompletedModelCall,
    DocumentAnalysisRequest,
    EngineAdvanceResult,
    PreparedModelCall,
    ResumableStageHost,
)
from novel_core.style_analysis.resumable_stages_metrics import (
    ResumableMetricsStagesMixin,
)
from novel_core.style_analysis.resumable_stages_semantic import (
    ResumableSemanticStagesMixin,
)
from novel_core.style_analysis.resumable_stages_structure import (
    ResumableStructureStagesMixin,
)
from novel_core.style_analysis.resumable_stages_terms import ResumableTermStagesMixin
from novel_core.style_analysis.runtime_models import AnalysisPolicy, RunStatus
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID
from novel_core.style_analysis.semantic_service import SemanticService
from novel_core.style_analysis.structure_service import StyleStructureService
from novel_core.style_analysis.term_service import TermService
from novel_core.style_analysis.text_service import StyleTextService

STAGE_ORDER = (
    "structure_prepare",
    "scene_boundary",
    "structure_finalize",
    "entity_mentions",
    "entity_resolver",
    "speaker_attribution",
    "pov",
    "term_candidates",
    "term_resolver",
    "term_explanation",
    "scene_semantics",
    "block_semantics",
    "semantic_metrics",
    "basic_metrics",
    "finalize",
)
STAGE_TOTAL = len(STAGE_ORDER)
_PROMPTS = {
    "scene_boundary": (
        "scene-boundary-detector",
        "style.scene_boundary",
        "style.scene_boundary.v1",
    ),
    "entity_mentions": (
        "entity-mention-extractor",
        "style.entity_mentions",
        "style.entity_mentions.v1",
    ),
    "entity_resolver": (
        "entity-resolver",
        "style.entity_resolution",
        "style.entity_resolution.v1",
    ),
    "speaker_attribution": (
        "speaker-attribution",
        "style.speaker_attribution",
        "style.speaker_attribution.v1",
    ),
    "pov": ("pov-classifier", "style.pov", "style.pov.v1"),
    "term_candidates": (
        "term-candidate-extractor",
        "style.term_candidates",
        "style.term_candidates.v1",
    ),
    "term_resolver": (
        "term-resolver",
        "style.term_resolution",
        "style.term_resolution.v1",
    ),
    "term_explanation": (
        "term-explanation-detector",
        "style.term_explanation",
        "style.term_explanation.v1",
    ),
    "scene_semantics": (
        "scene-semantic-classifier",
        "style.scene_semantics",
        "style.scene_semantics.classify.v1",
    ),
    "block_semantics": (
        "block-semantic-classifier",
        "style.block_semantic",
        "style.block_semantic.v1",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


_TAXONOMY_CONFIG = {
    "scene-semantic-classifier": {"scene_taxonomy_version": 1},
    "block-semantic-classifier": {"block_semantic_taxonomy_version": 1},
    "pov-classifier": {"pov_taxonomy_version": 1},
}
_METRIC_DEFINITIONS = {
    "style-metrics-basic": BASIC_METRIC_DEFINITIONS,
    "style-metrics-semantic": SEMANTIC_METRIC_DEFINITIONS,
}


class ResumableDocumentAnalysisEngine(
    ResumableStructureStagesMixin,
    ResumableSemanticStagesMixin,
    ResumableTermStagesMixin,
    ResumableMetricsStagesMixin,
    ResumableStageHost,
):
    """Transaction-neutral, one-model-call-at-a-time analysis state machine."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        model_provider: str,
        model_id: str,
        policy: AnalysisPolicy,
        checkpoint: Callable[[], None] | None = None,
        run_observer: Callable[[int, str], None] | None = None,
    ) -> None:
        self.connection = connection
        self.model_provider = model_provider
        self.model_id = model_id
        self.policy = policy
        self.checkpoint = checkpoint or (lambda: None)
        self.run_observer = run_observer or (lambda _run_id, _role: None)
        self.text = StyleTextService(connection)
        self.structure = StyleStructureService(connection)
        self.runs = AnalysisRunRepository(connection)
        self.runtime = AnalysisRuntime(self.runs)
        self.current_runs = CurrentRunResolver(connection, policy)
        self.entities = EntityService(connection)
        self.terms = TermService(connection)
        self.semantic = SemanticService(connection)
        self.measurements = MeasurementRepository(connection)
        self._stage_order = STAGE_ORDER
        self._prompt_map = _PROMPTS

    def advance(
        self,
        request: DocumentAnalysisRequest,
        cursor: JsonObject,
        completed_call: CompletedModelCall | None = None,
    ) -> EngineAdvanceResult:
        state = self._state(request, cursor)
        if completed_call is not None:
            self._consume_completed(request, state, completed_call)
        while True:
            self.checkpoint()
            stage = cast(str, state["stage"])
            if stage == "structure_prepare":
                self._prepare_structure(request, state)
                continue
            if stage == "scene_boundary":
                pending = self._boundary_call(state)
                if pending is not None:
                    return EngineAdvanceResult(
                        self._public_cursor(state), pending_call=pending
                    )
                continue
            if stage == "structure_finalize":
                self._finalize_structure(state)
                continue
            if stage in self._prompt_map:
                pending = self._model_stage_call(request, state)
                if pending is not None:
                    return EngineAdvanceResult(
                        self._public_cursor(state), pending_call=pending
                    )
                continue
            if stage == "semantic_metrics":
                self._finish_noop_stage(state, "style-metrics-semantic")
                continue
            if stage == "basic_metrics":
                self._finish_noop_stage(state, "style-metrics-basic")
                continue
            if stage == "finalize":
                self._finalize_document(state)
                return EngineAdvanceResult(
                    self._public_cursor(state), result=self._result(state)
                )
            raise ValueError("ANALYSIS_STAGE_INVALID")

    def _state(
        self, request: DocumentAnalysisRequest, cursor: JsonObject
    ) -> dict[str, Any]:
        if cursor.get("schema_version") != 1:
            raise ValueError("ANALYSIS_CURSOR_INVALID")
        if "document_id" in cursor:
            if any(
                cursor.get(key) != value
                for key, value in {
                    "document_id": request.document_id,
                    "text_revision_id": request.text_revision_id,
                }.items()
            ):
                raise ValueError("ANALYSIS_CURSOR_REQUEST_MISMATCH")
            return dict(cursor)
        if request.preset not in {"deterministic", "full", "metrics"}:
            raise ValueError("ANALYSIS_PRESET_INVALID")
        if request.structure_revision_id is not None and request.rebuild_structure:
            raise ValueError("STRUCTURE_REBUILD_CONFLICT")
        return {
            "schema_version": 1,
            "document_index": 0,
            "document_id": request.document_id,
            "text_revision_id": request.text_revision_id,
            "requested_structure_revision_id": request.structure_revision_id,
            "preset": request.preset,
            "rebuild_structure": request.rebuild_structure,
            "stage": "structure_prepare",
            "stage_index": 1,
            "stage_total": STAGE_TOTAL,
            "run_ids": [],
            "warnings": [],
            "stage_runs": {},
            "stage_responses": [],
            "stage_substage": "classify",
            "pending_call_key": None,
            "subject_index": 0,
            "run_id": None,
            "entity_resolved_by_scene": {},
            "term_resolved_by_scene": {},
            "term_novelty": {},
        }

    def _prepared(
        self,
        call_key: str,
        run_id: int,
        analyzer_id: str,
        prompt_id: str,
        contract_id: str,
        payload: JsonObject,
    ) -> PreparedModelCall:
        prompt = get_prompt(prompt_id)
        return PreparedModelCall(
            call_key=call_key,
            analysis_run_id=run_id,
            analyzer_id=analyzer_id,
            analyzer_version=ANALYZERS_BY_ID[analyzer_id].version,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            response_contract_id=contract_id,
            system_prompt=prompt.system_prompt,
            user_payload=payload,
            response_schema=ResponseContractRegistry.get(contract_id).schema,
        )

    def _ensure_run(
        self, state: dict[str, Any], analyzer_id: str, prompt_id: str | None
    ) -> int:
        stage = cast(str, state["stage"])
        stage_runs = cast(dict[str, Any], state.setdefault("stage_runs", {}))
        existing = stage_runs.get(stage)
        if isinstance(existing, int):
            state["run_id"] = existing
            return existing
        definition = ANALYZERS_BY_ID[analyzer_id]
        prompt = None if prompt_id is None else get_prompt(prompt_id)
        config = self._run_config(analyzer_id)
        config_json = canonical_json_bytes(cast(JsonValue, config)).decode()
        dependencies: list[Any] = []
        for dependency in definition.dependencies:
            dependency_id = self._dependency_run_id(state, dependency.analyzer_id)
            if (
                not dependency_id
                and state.get("preset") == "metrics"
                and analyzer_id == "style-metrics-semantic"
            ):
                current = self.current_runs.resolve(
                    int(state["document_id"]),
                    int(state["text_revision_id"]),
                    int(state["structure_revision_id"]),
                    dependency.analyzer_id,
                )
                dependency_id = 0 if current is None else current.id
            if not dependency_id:
                break
            dependency_run = self.runs.get_run(dependency_id)
            if dependency_run is None:
                break
            dependencies.append(dependency_run)
        dependency_pairs = tuple(
            (dependency.analyzer_id, dependency.id) for dependency in dependencies
        )
        if len(dependencies) == len(definition.dependencies):
            input_config, state_fingerprint, policy_fingerprint = (
                self.current_runs._inputs(
                    int(state["document_id"]),
                    int(state["text_revision_id"]),
                    int(state["structure_revision_id"]),
                    analyzer_id,
                    tuple(dependencies),
                )
            )
            config = cast(JsonObject, input_config)
            config_json = canonical_json_bytes(cast(JsonValue, config)).decode()
        else:
            state_fingerprint = None
            policy_fingerprint = None
        expectations = tuple(
            self.current_runs._expectation(dependency) for dependency in dependencies
        )
        model_provider = self.model_provider if prompt is not None else None
        model_id = self.model_id if prompt is not None else None
        if definition.cacheable and len(dependencies) == len(definition.dependencies):
            existing_run = self.runtime.resolve_cache_hit(
                document_id=int(state["document_id"]),
                analyzer_id=analyzer_id,
                text_revision_id=int(state["text_revision_id"]),
                structure_revision_id=int(state["structure_revision_id"]),
                analyzer_version=definition.version,
                config_json=config_json,
                state_fingerprint=state_fingerprint,
                policy_input_fingerprint=policy_fingerprint,
                dependency_runs=dependency_pairs,
                dependency_expectations=expectations,
                model_provider=model_provider,
                model_id=model_id,
                prompt_id=None if prompt is None else prompt.prompt_id,
                prompt_version=None if prompt is None else prompt.version,
            )
            if existing_run is not None:
                state["run_id"] = existing_run.id
                stage_runs[stage] = existing_run.id
                cast(list[object], state.setdefault("run_ids", [])).append(
                    existing_run.id
                )
                state["stage_reused"] = True
                self.run_observer(existing_run.id, "reused")
                return existing_run.id
        fingerprint = execution_fingerprint(
            analyzer_id=analyzer_id,
            analyzer_version=definition.version,
            text_revision_id=int(state["text_revision_id"]),
            structure_revision_id=int(state["structure_revision_id"]),
            config=cast(JsonValue, config),
            state_fingerprint=state_fingerprint,
            policy_input_fingerprint=policy_fingerprint,
            dependency_runs=dependency_pairs,
            model_provider=model_provider,
            model_id=model_id,
            prompt_id=None if prompt is None else prompt.prompt_id,
            prompt_version=None if prompt is None else prompt.version,
        )
        run_id = self.runs.insert_run(
            document_id=int(state["document_id"]),
            analyzer_id=analyzer_id,
            analyzer_version=definition.version,
            text_revision_id=int(state["text_revision_id"]),
            structure_revision_id=int(state["structure_revision_id"]),
            status="running",
            fingerprint=fingerprint,
            config_json=config_json,
            analysis_policy_version=self.policy.version,
            policy_input_fingerprint=policy_fingerprint,
            state_fingerprint=state_fingerprint,
            model_provider=model_provider,
            model_id=model_id,
            prompt_id=None if prompt is None else prompt.prompt_id,
            prompt_version=None if prompt is None else prompt.version,
            started_at=_now(),
        )
        for dependency in dependencies:
            self.runs.add_dependency(run_id, dependency.id)
        state["run_id"] = run_id
        stage_runs[stage] = run_id
        cast(list[object], state.setdefault("run_ids", [])).append(run_id)
        self.run_observer(run_id, "created")
        return run_id

    @staticmethod
    def _run_config(analyzer_id: str) -> JsonObject:
        if analyzer_id in _TAXONOMY_CONFIG:
            return cast(JsonObject, _TAXONOMY_CONFIG[analyzer_id])
        definitions = _METRIC_DEFINITIONS.get(analyzer_id)
        if definitions is None:
            return {}
        return {
            "metric_versions": {
                name: definition.version
                for name, definition in sorted(definitions.items())
            }
        }

    def _stage_run(self, state: dict[str, Any], stage: str) -> int | None:
        value = cast(dict[str, Any], state.get("stage_runs", {})).get(stage)
        return value if isinstance(value, int) else None

    def _finish_run(self, run_id: int, status: RunStatus = "succeeded") -> None:
        self.runs.finish_run(run_id, status=status, finished_at=_now())

    def _finish_stage(self, state: dict[str, Any], run_id: int) -> None:
        stage = cast(str, state["stage"])
        failed = bool(state.get("stage_errors", False))
        if stage == "term_resolver" and not failed:
            try:
                self._finish_term_resolution(state, run_id)
            except Exception as exc:
                failed = True
                state["stage_errors"] = True
                state["stage_error_code"] = type(exc).__name__
                state["stage_error_message"] = str(exc)
        state.pop("stage_errors", None)
        stage_warnings = cast(list[object], state.pop("stage_warnings", []))
        status: RunStatus = (
            "failed"
            if failed
            and stage in {"scene_boundary", "entity_mentions", "term_candidates"}
            else "partial"
            if failed or stage_warnings
            else "succeeded"
        )
        self.runs.finish_run(
            run_id,
            status=status,
            finished_at=_now(),
            error_code=(
                cast(str | None, state.pop("stage_error_code", None))
                if failed
                else None
            ),
            error_message=(
                cast(str | None, state.pop("stage_error_message", None))
                if failed
                else None
            ),
            warning_json=canonical_json_bytes(cast(JsonValue, stage_warnings)).decode(),
        )

    def _dependency_failed(self, state: dict[str, Any], analyzer_id: str) -> bool:
        definition = ANALYZERS_BY_ID[analyzer_id]
        if not definition.dependencies:
            return False
        run = self.runs.get_run(self._stage_run(state, cast(str, state["stage"])) or 0)
        return run is not None and any(
            (dependency := self.runs.get_run(dependency_id)) is not None
            and dependency.status == "failed"
            for _analyzer_id, dependency_id in run.dependency_runs
        )

    @staticmethod
    def _record_warning(state: dict[str, Any], warning: str) -> None:
        cast(list[object], state.setdefault("warnings", [])).append(warning)
        cast(list[object], state.setdefault("stage_warnings", [])).append(warning)

    def _record_warnings(self, state: dict[str, Any], warnings: object) -> None:
        if isinstance(warnings, list | tuple):
            for warning in warnings:
                self._record_warning(state, str(warning))

    def _next_stage(self, state: dict[str, Any]) -> None:
        stage = cast(str, state["stage"])
        if stage == "semantic_metrics" and state.get("preset") == "metrics":
            index = self._stage_order.index("finalize")
        elif stage == "basic_metrics":
            index = self._stage_order.index("finalize")
        else:
            index = self._stage_order.index(stage) + 1
        state["stage"] = self._stage_order[index]
        state["stage_index"] = index + 1
        state["subject_index"] = 0
        state["run_id"] = None
        state["chunk_index"] = 0
        state["stage_responses"] = []
        state["stage_substage"] = (
            "primary" if state["stage"] == "term_explanation" else "classify"
        )
        state["stage_scene_id"] = None
        state["stage_errors"] = False
        state["stage_error_code"] = None
        state["stage_error_message"] = None
        state["stage_warnings"] = []
        state["stage_fallback_available"] = False

    def _dependency_run_id(self, state: dict[str, Any], analyzer_id: str) -> int:
        for run_id in cast(list[int], state.get("run_ids", [])):
            run = self.runs.get_run(run_id)
            if run is not None and run.analyzer_id == analyzer_id:
                return run.id
        if state.get("preset") == "metrics":
            current = self.current_runs.resolve(
                int(state["document_id"]),
                int(state["text_revision_id"]),
                int(state["structure_revision_id"]),
                analyzer_id,
            )
            if current is not None:
                return current.id
        return 0

    def _result(self, state: dict[str, Any]) -> Any:
        from novel_core.style_analysis.analysis_orchestrator import (
            DocumentAnalysisResult,
        )

        warnings = [
            str(warning) for warning in cast(list[object], state.get("warnings", []))
        ]
        for run_id in cast(list[int], state.get("run_ids", [])):
            run = self.runs.get_run(run_id)
            if run is not None and run.status != "succeeded":
                marker = f"ANALYZER_{run.status.upper()}:{run.analyzer_id}"
                if marker not in warnings:
                    warnings.append(marker)
        return DocumentAnalysisResult(
            status="partial" if warnings else "succeeded",
            text_revision_id=int(state["text_revision_id"]),
            structure_revision_id=int(state["structure_revision_id"]),
            run_ids=tuple(cast(list[int], state.get("run_ids", []))),
            warnings=tuple(warnings),
            metrics=tuple(cast(tuple[StoredJsonObject, ...], state.get("metrics", ()))),
        )

    def _finalize_document(self, state: dict[str, Any]) -> None:
        if not state.get("pointer_update_allowed"):
            return
        document_id = int(state["document_id"])
        cursor = self.connection.execute(
            "UPDATE style_documents SET current_structure_revision_id = ? "
            "WHERE id = ? AND current_text_revision_id IS ? "
            "AND current_structure_revision_id IS ?",
            (
                int(state["structure_revision_id"]),
                document_id,
                state.get("initial_current_text_revision_id"),
                state.get("initial_current_structure_revision_id"),
            ),
        )
        if cursor.rowcount != 1:
            current = self.text.get_document(document_id)
            warning = (
                "CURRENT_TEXT_CHANGED"
                if current is not None
                and current.current_text_revision_id
                != state.get("initial_current_text_revision_id")
                else "CURRENT_STRUCTURE_CHANGED"
            )
            self._record_warning(state, warning)
