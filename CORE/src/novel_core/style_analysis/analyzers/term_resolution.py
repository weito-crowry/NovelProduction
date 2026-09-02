from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from novel_core.style_analysis.model_contracts import (
    JsonObject,
    ModelClient,
    ModelRequest,
    complete_validated_json,
    require_int,
    validate_confidence,
    validate_model_object,
    validate_positive_id,
)
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.term_models import TERM_TYPES


@dataclass(frozen=True, slots=True)
class TermResolutionDecision:
    decision: str
    term_id: int | None
    new_term_type: str | None
    new_canonical_label: str | None
    confidence: float


def resolve_term_candidate(
    *,
    candidate: JsonObject,
    previous_blocks: Sequence[JsonObject],
    subject_block: JsonObject,
    next_blocks: Sequence[JsonObject],
    candidates: Sequence[JsonObject],
    auto_merge_threshold: float,
    client: ModelClient,
) -> TermResolutionDecision:
    prompt = get_prompt("style.term_resolution")
    response = complete_validated_json(
        client,
        ModelRequest(
            prompt.prompt_id,
            prompt.version,
            prompt.system_prompt,
            {
                "candidate": candidate,
                "previous_blocks": list(previous_blocks),
                "subject_block": subject_block,
                "next_blocks": list(next_blocks),
                "candidates": list(candidates),
            },
        ),
        _validate_response_shape,
    )
    obj = validate_model_object(
        response,
        required=(
            "decision",
            "term_id",
            "new_term_type",
            "new_canonical_label",
            "confidence",
        ),
        allowed=(
            "decision",
            "term_id",
            "new_term_type",
            "new_canonical_label",
            "confidence",
        ),
    )
    decision = obj["decision"]
    if decision not in {"existing", "new", "unresolved"}:
        raise ValueError("DECISION_INVALID")
    confidence = validate_confidence(obj["confidence"])
    candidate_ids = {
        require_int(item["term_id"])
        for item in candidates
        if isinstance(item.get("term_id"), int)
        and not isinstance(item.get("term_id"), bool)
    }
    term_id = validate_positive_id(obj["term_id"], nullable=True)
    new_type = obj["new_term_type"]
    new_label = obj["new_canonical_label"]
    if decision == "existing":
        if (
            term_id is None
            or term_id not in candidate_ids
            or new_type is not None
            or new_label is not None
        ):
            raise ValueError("MODEL_CONTRACT_INVALID")
        if confidence < auto_merge_threshold:
            return TermResolutionDecision("unresolved", None, None, None, confidence)
    elif decision == "new":
        if (
            term_id is not None
            or not isinstance(new_type, str)
            or new_type not in TERM_TYPES
            or not isinstance(new_label, str)
            or not new_label
        ):
            raise ValueError("MODEL_CONTRACT_INVALID")
        if confidence < auto_merge_threshold:
            return TermResolutionDecision("unresolved", None, None, None, confidence)
    elif term_id is not None or new_type is not None or new_label is not None:
        raise ValueError("MODEL_CONTRACT_INVALID")
    return TermResolutionDecision(
        str(decision),
        term_id,
        new_type if isinstance(new_type, str) else None,
        new_label if isinstance(new_label, str) else None,
        confidence,
    )


def _validate_response_shape(value: JsonObject) -> JsonObject:
    return validate_model_object(
        value,
        required=(
            "decision",
            "term_id",
            "new_term_type",
            "new_canonical_label",
            "confidence",
        ),
        allowed=(
            "decision",
            "term_id",
            "new_term_type",
            "new_canonical_label",
            "confidence",
        ),
    )
