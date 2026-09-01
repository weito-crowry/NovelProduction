from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from novel_core.style_analysis.entity_models import ENTITY_TYPES, MENTION_TYPES
from novel_core.style_analysis.model_contracts import (
    JsonObject,
    ModelClient,
    ModelRequest,
    require_int,
    validate_confidence,
    validate_model_object,
    validate_positive_id,
)
from novel_core.style_analysis.model_prompts import get_prompt


@dataclass(frozen=True, slots=True)
class EntityResolutionDecision:
    decision: str
    entity_id: int | None
    new_entity_type: str | None
    new_canonical_name: str | None
    confidence: float


def resolve_entity_mention(
    *,
    mention: JsonObject,
    previous_blocks: Sequence[JsonObject],
    subject_block: JsonObject,
    next_blocks: Sequence[JsonObject],
    candidates: Sequence[JsonObject],
    auto_merge_threshold: float,
    client: ModelClient,
) -> EntityResolutionDecision:
    mention_type = mention.get("mention_type")
    if mention_type not in MENTION_TYPES:
        raise ValueError("MENTION_TYPE_INVALID")
    prompt = get_prompt("style.entity_resolution")
    response = client.complete_json(
        ModelRequest(
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            system_prompt=prompt.system_prompt,
            user_payload={
                "mention": mention,
                "previous_blocks": list(previous_blocks),
                "subject_block": subject_block,
                "next_blocks": list(next_blocks),
                "candidates": list(candidates),
            },
        )
    )
    obj = validate_model_object(
        response,
        required=(
            "decision",
            "entity_id",
            "new_entity_type",
            "new_canonical_name",
            "confidence",
        ),
        allowed=(
            "decision",
            "entity_id",
            "new_entity_type",
            "new_canonical_name",
            "confidence",
        ),
    )
    decision = obj["decision"]
    if decision not in {"existing", "new", "unresolved"}:
        raise ValueError("DECISION_INVALID")
    confidence = validate_confidence(obj["confidence"])
    candidate_ids = {
        require_int(candidate["entity_id"])
        for candidate in candidates
        if isinstance(candidate.get("entity_id"), int)
        and not isinstance(candidate.get("entity_id"), bool)
    }
    entity_id = validate_positive_id(obj["entity_id"], nullable=True)
    new_type = obj["new_entity_type"]
    new_name = obj["new_canonical_name"]
    if decision == "existing":
        if (
            entity_id is None
            or entity_id not in candidate_ids
            or new_type is not None
            or new_name is not None
        ):
            raise ValueError("MODEL_CONTRACT_INVALID")
        if confidence < auto_merge_threshold:
            return EntityResolutionDecision("unresolved", None, None, None, confidence)
    elif decision == "new":
        if (
            entity_id is not None
            or not isinstance(new_type, str)
            or new_type not in ENTITY_TYPES
            or not isinstance(new_name, str)
            or not new_name
            or mention_type in {"pronoun", "role_title"}
        ):
            raise ValueError("MODEL_CONTRACT_INVALID")
        if confidence < auto_merge_threshold:
            return EntityResolutionDecision("unresolved", None, None, None, confidence)
    else:
        if entity_id is not None or new_type is not None or new_name is not None:
            raise ValueError("MODEL_CONTRACT_INVALID")
    return EntityResolutionDecision(
        str(decision),
        entity_id,
        new_type if isinstance(new_type, str) else None,
        new_name if isinstance(new_name, str) else None,
        confidence,
    )
