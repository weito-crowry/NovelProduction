from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from novel_core.style_analysis.model_contracts import JsonObject
from novel_core.style_analysis.resolver_candidates import build_context_window

if TYPE_CHECKING:
    from novel_core.style_analysis.aggregate_repository import MeasurementRepository
    from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisResult
    from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
    from novel_core.style_analysis.entity_service import EntityService
    from novel_core.style_analysis.runtime_models import AnalysisPolicy, RunStatus
    from novel_core.style_analysis.semantic_service import SemanticService
    from novel_core.style_analysis.structure_service import StyleStructureService
    from novel_core.style_analysis.term_service import TermService
    from novel_core.style_analysis.text_service import StyleTextService


@dataclass(frozen=True, slots=True)
class DocumentAnalysisRequest:
    document_id: int
    text_revision_id: int
    structure_revision_id: int | None = None
    preset: str = "full"
    rebuild_structure: bool = False


ResumableAnalysisRequest = DocumentAnalysisRequest


@dataclass(frozen=True, slots=True)
class PreparedModelCall:
    call_key: str
    analysis_run_id: int
    analyzer_id: str
    analyzer_version: int
    prompt_id: str
    prompt_version: int
    response_contract_id: str
    system_prompt: str
    user_payload: JsonObject
    response_schema: JsonObject


@dataclass(frozen=True, slots=True)
class CompletedModelCall:
    call_key: str
    response: JsonObject | None = None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        successful = self.response is not None
        failed = self.error_code is not None
        if successful == failed:
            raise ValueError("COMPLETED_MODEL_CALL_INVALID")
        if successful and self.error_message is not None:
            raise ValueError("COMPLETED_MODEL_CALL_INVALID")
        if failed and self.response is not None:
            raise ValueError("COMPLETED_MODEL_CALL_INVALID")


@dataclass(frozen=True, slots=True)
class EngineAdvanceResult:
    cursor: JsonObject
    pending_call: PreparedModelCall | None = None
    result: DocumentAnalysisResult | None = None

    def __post_init__(self) -> None:
        if (self.pending_call is None) == (self.result is None):
            raise ValueError("ENGINE_ADVANCE_RESULT_INVALID")


class ResumableStageHost:
    """Typing surface shared by the split engine stage mixins."""

    connection: sqlite3.Connection
    text: StyleTextService
    structure: StyleStructureService
    runs: AnalysisRunRepository
    entities: EntityService
    terms: TermService
    semantic: SemanticService
    measurements: MeasurementRepository
    policy: AnalysisPolicy
    checkpoint: Callable[[], None]
    _stage_order: tuple[str, ...]
    _prompt_map: dict[str, tuple[str, str, str]]

    def _boundary_call(self, state: dict[str, Any]) -> PreparedModelCall | None:
        raise NotImplementedError

    def _model_stage_call(
        self, request: DocumentAnalysisRequest, state: dict[str, Any]
    ) -> PreparedModelCall | None:
        raise NotImplementedError

    def _current_spec(
        self, stage: str, request: DocumentAnalysisRequest, state: dict[str, Any]
    ) -> tuple[str, JsonObject, str | None] | None:
        raise NotImplementedError

    def _prepared(
        self,
        call_key: str,
        run_id: int,
        analyzer_id: str,
        prompt_id: str,
        contract_id: str,
        payload: JsonObject,
    ) -> PreparedModelCall:
        raise NotImplementedError

    def _ensure_run(
        self, state: dict[str, Any], analyzer_id: str, prompt_id: str | None
    ) -> int:
        raise NotImplementedError

    def _finish_run(self, run_id: int, status: RunStatus = "succeeded") -> None:
        raise NotImplementedError

    def _finish_stage(self, state: dict[str, Any], run_id: int) -> None:
        raise NotImplementedError

    def _dependency_failed(self, state: dict[str, Any], analyzer_id: str) -> bool:
        raise NotImplementedError

    def _record_warning(self, state: dict[str, Any], warning: str) -> None:
        raise NotImplementedError

    def _record_warnings(self, state: dict[str, Any], warnings: object) -> None:
        raise NotImplementedError

    def _next_stage(self, state: dict[str, Any]) -> None:
        raise NotImplementedError

    def _stage_run(self, state: dict[str, Any], stage: str) -> int | None:
        raise NotImplementedError

    def _dependency_run_id(self, state: dict[str, Any], analyzer_id: str) -> int:
        raise NotImplementedError

    def _advance_after_call(
        self, state: dict[str, Any], response: JsonObject | None
    ) -> None:
        raise NotImplementedError

    def _advance_scene_chunks(
        self, state: dict[str, Any], response: JsonObject | None, *, boundary: bool
    ) -> None:
        raise NotImplementedError

    def _apply_model_response(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        raise NotImplementedError

    def _apply_term_resolution(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        raise NotImplementedError

    def _apply_term_explanation(
        self, state: dict[str, Any], response: JsonObject
    ) -> None:
        raise NotImplementedError

    def _restore_pending_payload(
        self, request: DocumentAnalysisRequest, state: dict[str, Any], call_key: str
    ) -> None:
        raise NotImplementedError

    @staticmethod
    def _block_json(block: Any, text: str) -> JsonObject:
        return {
            "block_id": block.id,
            "scene_id": block.scene_id,
            "order_index": block.order_index,
            "block_type": block.block_type,
            "text": text[block.start_cp : block.end_cp],
        }

    @staticmethod
    def _block_start(blocks: Any, block_id: int) -> int:
        for block in blocks:
            if block.id == block_id:
                return int(block.start_cp)
        raise ValueError("BLOCK_NOT_FOUND")

    @staticmethod
    def _context(
        blocks: Any, block_id: int, before: int, after: int
    ) -> tuple[list[JsonObject], JsonObject, list[JsonObject]]:
        return build_context_window(
            blocks, subject_block_id=block_id, before=before, after=after
        )

    def _people_for_scene(
        self, document_id: int, resolution_run_id: int, scene_id: int | None
    ) -> list[JsonObject]:
        from novel_core.style_analysis.analysis_orchestrator_state import (
            AnalysisStateReader,
        )

        return AnalysisStateReader(self.connection)._people_for_scene(
            document_id, resolution_run_id, scene_id
        )

    def _complete_deterministic_subject(
        self, state: dict[str, Any], stage: str
    ) -> bool:
        raise NotImplementedError

    def _complete_deterministic_term(
        self, state: dict[str, Any], marker: dict[str, Any], run_id: int
    ) -> bool:
        raise NotImplementedError

    @staticmethod
    def _remember_resolved(
        state: dict[str, Any], key: str, scene_id: int, identity_id: int
    ) -> None:
        raise NotImplementedError

    @staticmethod
    def _remember_novelty(
        state: dict[str, Any], term_id: int, novelty: str, confidence: float
    ) -> None:
        raise NotImplementedError

    def _finish_term_resolution(self, state: dict[str, Any], run_id: int) -> None:
        raise NotImplementedError

    def _previous_context(
        self, blocks: list[JsonObject], scene_id: int
    ) -> list[JsonObject]:
        current = [item for item in blocks if item.get("scene_id") == scene_id]
        first_order = current[0].get("order_index") if current else 0
        return [
            item
            for item in blocks
            if isinstance(item.get("order_index"), int)
            and isinstance(first_order, int)
            and int(cast(Any, item["order_index"])) < first_order
            and item.get("scene_id") is not None
        ][-3:]

    @staticmethod
    def _annotation_value(value_json: str) -> JsonObject:
        value = json.loads(value_json)
        if not isinstance(value, dict):
            raise ValueError("ANNOTATION_VALUE_INVALID")
        return cast(JsonObject, value)
