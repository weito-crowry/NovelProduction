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
from novel_core.style_analysis.analyzers.pov_classifier import (
    validate_pov_response,
)
from novel_core.style_analysis.analyzers.scene_boundary import (
    _validate_response_shape as validate_scene_boundary_shape,
)
from novel_core.style_analysis.analyzers.scene_classifier import (
    _validate_scene_response,
)
from novel_core.style_analysis.analyzers.speaker_attribution import SPEAKER_REASONS
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
from novel_core.style_analysis.entity_models import ENTITY_TYPES, MENTION_TYPES
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.model_contracts import (
    REPAIR_SYSTEM_PROMPT,
    JsonObject,
    validate_model_object,
)
from novel_core.style_analysis.resumable_models import PreparedModelCall
from novel_core.style_analysis.semantic_models import (
    BLOCK_PRIMARY_LABELS,
    BOUNDARY_REASONS,
    POV_MODES,
    SCENE_FUNCTIONS,
    SCENE_INFORMATION_LOADS,
    SCENE_INTERACTIONS,
    SCENE_PACES,
    SCENE_TONES,
)
from novel_core.style_analysis.term_models import NOVELTY_VALUES, TERM_TYPES

RepairableValidator = Callable[[JsonObject], JsonObject]
RequestAwareValidator = Callable[[JsonObject, JsonObject], JsonObject]


@dataclass(frozen=True, slots=True)
class ResponseContract:
    schema: JsonObject
    validator: RepairableValidator
    request_validator: RequestAwareValidator | None = None


def _object(
    properties: Mapping[str, JsonObject], required: tuple[str, ...]
) -> JsonObject:
    return {
        "type": "object",
        "properties": cast(JsonValue, dict(properties)),
        "required": list(required),
        "additionalProperties": False,
    }


def _string(*, min_length: int = 0) -> JsonObject:
    value: JsonObject = {"type": "string"}
    if min_length:
        value["minLength"] = min_length
    return value


def _integer(*, minimum: int | None = None) -> JsonObject:
    value: JsonObject = {"type": "integer"}
    if minimum is not None:
        value["minimum"] = minimum
    return value


def _number(
    *, minimum: float | None = None, maximum: float | None = None
) -> JsonObject:
    value: JsonObject = {"type": "number"}
    if minimum is not None:
        value["minimum"] = minimum
    if maximum is not None:
        value["maximum"] = maximum
    return value


def _enum(values: frozenset[str]) -> JsonObject:
    return {"type": "string", "enum": sorted(values)}


def _array(items: JsonObject, *, min_items: int | None = None) -> JsonObject:
    value: JsonObject = {"type": "array", "items": items}
    if min_items is not None:
        value["minItems"] = min_items
    return value


def _nullable_positive_id() -> JsonObject:
    return {"oneOf": [_integer(minimum=1), {"type": "null"}]}


def _confidence() -> JsonObject:
    return _number(minimum=0.0, maximum=1.0)


def _label(choices: frozenset[str]) -> JsonObject:
    return _object(
        {"label": _enum(choices), "confidence": _confidence()},
        ("label", "confidence"),
    )


def _block_item(
    properties: Mapping[str, JsonObject], required: tuple[str, ...]
) -> JsonObject:
    return _object(
        {
            "block_id": _integer(minimum=1),
            **dict(properties),
            "start_in_block": _integer(minimum=0),
            "end_in_block": _integer(minimum=0),
            "confidence": _confidence(),
        },
        required,
    )


_BOUNDARY_ITEM = _object(
    {
        "after_block_id": _integer(minimum=1),
        "reasons": _array(_enum(BOUNDARY_REASONS), min_items=1),
        "confidence": _confidence(),
    },
    ("after_block_id", "reasons", "confidence"),
)
_MENTION_ITEM = _block_item(
    {
        "surface": _string(min_length=1),
        "mention_type": _enum(MENTION_TYPES),
        "entity_type_candidate": _enum(ENTITY_TYPES),
        "canonical_name_candidate": _string(min_length=1),
    },
    (
        "block_id",
        "surface",
        "start_in_block",
        "end_in_block",
        "mention_type",
        "entity_type_candidate",
        "canonical_name_candidate",
        "confidence",
    ),
)
_ENTITY_RESOLUTION = _object(
    {
        "decision": _enum(frozenset({"existing", "new", "unresolved"})),
        "entity_id": _nullable_positive_id(),
        "new_entity_type": {"oneOf": [_enum(ENTITY_TYPES), {"type": "null"}]},
        "new_canonical_name": {"oneOf": [_string(min_length=1), {"type": "null"}]},
        "confidence": _confidence(),
    },
    (
        "decision",
        "entity_id",
        "new_entity_type",
        "new_canonical_name",
        "confidence",
    ),
)
_SPEAKER = _object(
    {
        "speaker_entity_id": _nullable_positive_id(),
        "confidence": _confidence(),
        "evidence_block_ids": _array(_integer(minimum=1)),
        "reason_code": _enum(SPEAKER_REASONS),
    },
    ("speaker_entity_id", "confidence", "evidence_block_ids", "reason_code"),
)
_TERM_ITEM = _block_item(
    {
        "surface": _string(min_length=1),
        "canonical_label_candidate": _string(min_length=1),
        "term_type_candidate": _enum(TERM_TYPES),
        "novelty_candidate": _enum(NOVELTY_VALUES),
    },
    (
        "block_id",
        "surface",
        "start_in_block",
        "end_in_block",
        "canonical_label_candidate",
        "term_type_candidate",
        "novelty_candidate",
        "confidence",
    ),
)
_TERM_RESOLUTION = _object(
    {
        "decision": _enum(frozenset({"existing", "new", "unresolved"})),
        "term_id": _nullable_positive_id(),
        "new_term_type": {"oneOf": [_enum(TERM_TYPES), {"type": "null"}]},
        "new_canonical_label": {"oneOf": [_string(min_length=1), {"type": "null"}]},
        "confidence": _confidence(),
    },
    (
        "decision",
        "term_id",
        "new_term_type",
        "new_canonical_label",
        "confidence",
    ),
)
_EXPLANATION_ITEM = _block_item(
    {
        "explanation_kind": _enum(
            frozenset(
                {
                    "definition",
                    "paraphrase",
                    "example",
                    "contextual_clue",
                    "contrast",
                    "other",
                }
            )
        ),
        "completeness": _enum(frozenset({"partial", "sufficient"})),
    },
    (
        "block_id",
        "start_in_block",
        "end_in_block",
        "explanation_kind",
        "completeness",
        "confidence",
    ),
)
_SCENE_CLASSIFY = _object(
    {
        "function": _array(_label(SCENE_FUNCTIONS), min_items=1),
        "tone": _array(_label(SCENE_TONES), min_items=1),
        "pace": _label(SCENE_PACES),
        "information_load": _label(SCENE_INFORMATION_LOADS),
        "interaction": _label(SCENE_INTERACTIONS),
    },
    ("function", "tone", "pace", "information_load", "interaction"),
)
_SCENE_REDUCE = _object(
    {
        "pace": _label(SCENE_PACES),
        "information_load": _label(SCENE_INFORMATION_LOADS),
        "interaction": _label(SCENE_INTERACTIONS),
    },
    ("pace", "information_load", "interaction"),
)
_BLOCK_SEMANTIC = _object(
    {"label": _enum(BLOCK_PRIMARY_LABELS), "confidence": _confidence()},
    ("label", "confidence"),
)
_POV = _object(
    {
        "pov_mode": _enum(POV_MODES),
        "pov_entity_id": _nullable_positive_id(),
        "confidence": _confidence(),
    },
    ("pov_mode", "pov_entity_id", "confidence"),
)


def _shape_only(*keys: str) -> RepairableValidator:
    return lambda value: validate_model_object(value, required=keys, allowed=keys)


def _scene_classify(value: JsonObject) -> JsonObject:
    return _validate_scene_response(value, allow_reduce=False)


def _scene_reduce(value: JsonObject) -> JsonObject:
    return _validate_scene_response(value, allow_reduce=True)


def _pov_shape(value: JsonObject) -> JsonObject:
    return validate_model_object(
        value,
        required=("pov_mode", "pov_entity_id", "confidence"),
        allowed=("pov_mode", "pov_entity_id", "confidence"),
    )


def _pov_request(value: JsonObject, payload: JsonObject) -> JsonObject:
    people = payload.get("people")
    if not isinstance(people, list):
        raise ValueError("POV_PEOPLE_REQUIRED")
    return validate_pov_response(value, cast(list[JsonObject], people))


_CONTRACTS: Mapping[str, ResponseContract] = MappingProxyType(
    {
        "style.scene_boundary.v1": ResponseContract(
            _object({"boundaries": _array(_BOUNDARY_ITEM)}, ("boundaries",)),
            validate_scene_boundary_shape,
        ),
        "style.entity_mentions.v1": ResponseContract(
            _object({"mentions": _array(_MENTION_ITEM)}, ("mentions",)),
            validate_entity_mentions_shape,
        ),
        "style.entity_resolution.v1": ResponseContract(
            _ENTITY_RESOLUTION,
            validate_entity_resolution_shape,
        ),
        "style.speaker_attribution.v1": ResponseContract(
            _SPEAKER,
            validate_speaker_shape,
        ),
        "style.term_candidates.v1": ResponseContract(
            _object({"terms": _array(_TERM_ITEM)}, ("terms",)),
            validate_term_candidates_shape,
        ),
        "style.term_resolution.v1": ResponseContract(
            _TERM_RESOLUTION,
            validate_term_resolution_shape,
        ),
        "style.term_explanation.v1": ResponseContract(
            _object({"explanations": _array(_EXPLANATION_ITEM)}, ("explanations",)),
            validate_term_explanation_shape,
        ),
        "style.scene_semantics.classify.v1": ResponseContract(
            _SCENE_CLASSIFY,
            _scene_classify,
        ),
        "style.scene_semantics.reduce.v1": ResponseContract(
            _SCENE_REDUCE,
            _scene_reduce,
        ),
        "style.block_semantic.v1": ResponseContract(
            _BLOCK_SEMANTIC,
            _shape_only("label", "confidence"),
        ),
        "style.pov.v1": ResponseContract(
            _POV,
            _pov_shape,
            _pov_request,
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
    def validate(
        contract_id: str, response: JsonObject, user_payload: JsonObject | None = None
    ) -> JsonObject:
        contract = ResponseContractRegistry.get(contract_id)
        value = contract.validator(response)
        if contract.request_validator is not None:
            if user_payload is None:
                raise ValueError("RESPONSE_REQUEST_CONTEXT_REQUIRED")
            value = contract.request_validator(value, user_payload)
        return value

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
