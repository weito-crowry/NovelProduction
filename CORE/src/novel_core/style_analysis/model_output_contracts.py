from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from novel_core.style_analysis.analyzers.entity_mentions import (
    _validate_response_shape as validate_entity_mentions_shape,
)
from novel_core.style_analysis.analyzers.entity_resolution import (
    _validate_response_shape as validate_entity_resolution_shape,
)
from novel_core.style_analysis.analyzers.scene_boundary import (
    _validate_response_shape as validate_scene_boundary_shape,
)
from novel_core.style_analysis.analyzers.scene_classifier import (
    _validate_scene_response,
)
from novel_core.style_analysis.analyzers.speaker_attribution import (
    _validate_response_shape as validate_speaker_shape,
)
from novel_core.style_analysis.analyzers.term_candidates import (
    _validate_response_shape as validate_term_candidates_shape,
)
from novel_core.style_analysis.analyzers.term_explanation import (
    _validate_response_shape as validate_term_explanation_shape,
)
from novel_core.style_analysis.analyzers.term_resolution import (
    _validate_response_shape as validate_term_resolution_shape,
)
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.model_contracts import (
    REPAIR_SYSTEM_PROMPT,
    JsonObject,
    validate_model_object,
)
from novel_core.style_analysis.resumable_models import PreparedModelCall

RepairableValidator = Callable[[JsonObject], JsonObject]


@dataclass(frozen=True, slots=True)
class ResponseContract:
    schema: JsonObject
    validator: RepairableValidator


def _required(*keys: str) -> JsonObject:
    return {"type": "object", "required": list(keys), "additionalProperties": False}


def _shape_only(*keys: str) -> RepairableValidator:
    return lambda value: validate_model_object(value, required=keys, allowed=keys)


def _scene_classify(value: JsonObject) -> JsonObject:
    return _validate_scene_response(value, allow_reduce=False)


def _scene_reduce(value: JsonObject) -> JsonObject:
    return _validate_scene_response(value, allow_reduce=True)


_CONTRACTS: Mapping[str, ResponseContract] = MappingProxyType(
    {
        "style.scene_boundary.v1": ResponseContract(
            _required("boundaries"), validate_scene_boundary_shape
        ),
        "style.entity_mentions.v1": ResponseContract(
            _required("mentions"), validate_entity_mentions_shape
        ),
        "style.entity_resolution.v1": ResponseContract(
            _required(
                "decision",
                "entity_id",
                "new_entity_type",
                "new_canonical_name",
                "confidence",
            ),
            validate_entity_resolution_shape,
        ),
        "style.speaker_attribution.v1": ResponseContract(
            _required(
                "speaker_entity_id", "confidence", "evidence_block_ids", "reason_code"
            ),
            validate_speaker_shape,
        ),
        "style.term_candidates.v1": ResponseContract(
            _required("terms"), validate_term_candidates_shape
        ),
        "style.term_resolution.v1": ResponseContract(
            _required(
                "decision",
                "term_id",
                "new_term_type",
                "new_canonical_label",
                "confidence",
            ),
            validate_term_resolution_shape,
        ),
        "style.term_explanation.v1": ResponseContract(
            _required("explanations"), validate_term_explanation_shape
        ),
        "style.scene_semantics.classify.v1": ResponseContract(
            _required("function", "tone", "pace", "information_load", "interaction"),
            _scene_classify,
        ),
        "style.scene_semantics.reduce.v1": ResponseContract(
            _required("pace", "information_load", "interaction"), _scene_reduce
        ),
        "style.block_semantic.v1": ResponseContract(
            _required("label", "confidence"), _shape_only("label", "confidence")
        ),
        "style.pov.v1": ResponseContract(
            _required("pov_mode", "pov_entity_id", "confidence"),
            _shape_only("pov_mode", "pov_entity_id", "confidence"),
        ),
    }
)

RESPONSE_CONTRACT_IDS = tuple(_CONTRACTS)


class ResponseContractRegistry:
    @staticmethod
    def get(contract_id: str) -> ResponseContract:
        try:
            return _CONTRACTS[contract_id]
        except KeyError as exc:
            raise ValueError("RESPONSE_CONTRACT_NOT_FOUND") from exc

    @staticmethod
    def repair_system_prompt() -> str:
        return REPAIR_SYSTEM_PROMPT


def task_request_fingerprint(call: PreparedModelCall, *, attempt_no: int) -> str:
    return fingerprint_json(
        cast(
            JsonValue,
            {
                "call_key": call.call_key,
                "attempt_no": attempt_no,
                "analyzer_id": call.analyzer_id,
                "analyzer_version": call.analyzer_version,
                "prompt_id": call.prompt_id,
                "prompt_version": call.prompt_version,
                "response_contract_id": call.response_contract_id,
                "system_prompt": call.system_prompt,
                "user_payload": call.user_payload,
                "response_schema": call.response_schema,
            },
        )
    )
