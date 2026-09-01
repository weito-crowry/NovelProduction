from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
from novel_core.style_analysis.semantic_models import BOUNDARY_REASONS


@dataclass(frozen=True, slots=True)
class BoundaryCandidate:
    after_block_id: int
    reasons: tuple[str, ...]
    confidence: float


def detect_scene_boundaries(
    *,
    base_structure_revision_id: int,
    scene_id: int,
    blocks: Sequence[JsonObject],
    existing_after_block_ids: set[int] | frozenset[int] = frozenset(),
    client: ModelClient,
) -> tuple[BoundaryCandidate, ...]:
    prompt = get_prompt("style.scene_boundary")
    response = client.complete_json(
        ModelRequest(
            prompt.prompt_id,
            prompt.version,
            prompt.system_prompt,
            {
                "base_structure_revision_id": base_structure_revision_id,
                "scene_id": scene_id,
                "blocks": list(blocks),
            },
        )
    )
    obj = validate_model_object(
        response, required=("boundaries",), allowed=("boundaries",)
    )
    values = obj["boundaries"]
    if not isinstance(values, list):
        raise ValueError("MODEL_CONTRACT_INVALID")
    block_ids = [
        require_int(block["block_id"])
        for block in blocks
        if isinstance(block.get("block_id"), int)
    ]
    allowed_after = set(block_ids[:-1]) - set(existing_after_block_ids)
    merged: dict[int, BoundaryCandidate] = {}
    for value in values:
        item = validate_model_object(
            value,
            required=("after_block_id", "reasons", "confidence"),
            allowed=("after_block_id", "reasons", "confidence"),
        )
        after_id = validate_positive_id(item["after_block_id"])
        assert after_id is not None
        if after_id not in allowed_after:
            raise ValueError("MODEL_ITEM_BOUNDARY_INVALID")
        reasons_value = item["reasons"]
        if not isinstance(reasons_value, list) or not reasons_value:
            raise ValueError("MODEL_ITEM_ENUM_INVALID")
        reasons = tuple(sorted({str(reason) for reason in reasons_value}))
        if any(reason not in BOUNDARY_REASONS for reason in reasons):
            raise ValueError("MODEL_ITEM_ENUM_INVALID")
        candidate = BoundaryCandidate(
            after_id, reasons, validate_confidence(item["confidence"])
        )
        old = merged.get(after_id)
        if old is None or candidate.confidence > old.confidence:
            merged[after_id] = candidate
        elif candidate.confidence == old.confidence:
            merged[after_id] = BoundaryCandidate(
                after_id,
                tuple(sorted(set(old.reasons) | set(candidate.reasons))),
                old.confidence,
            )
    return tuple(merged[key] for key in sorted(merged))
