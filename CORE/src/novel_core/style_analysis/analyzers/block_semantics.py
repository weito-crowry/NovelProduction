from __future__ import annotations

from collections.abc import Sequence

from novel_core.style_analysis.model_contracts import (
    JsonObject,
    ModelClient,
    ModelRequest,
    require_int,
    validate_confidence,
    validate_enum,
    validate_model_object,
)
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.semantic_models import BLOCK_PRIMARY_LABELS


def classify_narration_block(
    *, block_id: int, text: str, client: ModelClient
) -> JsonObject:
    prompt = get_prompt("style.block_semantic")
    response = client.complete_json(
        ModelRequest(
            prompt.prompt_id,
            prompt.version,
            prompt.system_prompt,
            {"block_id": block_id, "text": text},
        )
    )
    obj = validate_model_object(
        response, required=("label", "confidence"), allowed=("label", "confidence")
    )
    validate_enum(obj["label"], BLOCK_PRIMARY_LABELS, code="SEMANTIC_LABEL")
    validate_confidence(obj["confidence"])
    return obj


def classify_narration_blocks(
    *, blocks: Sequence[JsonObject], client: ModelClient
) -> tuple[tuple[int, JsonObject], ...]:
    return tuple(
        (
            require_int(block["block_id"]),
            classify_narration_block(
                block_id=require_int(block["block_id"]),
                text=str(block["text"]),
                client=client,
            ),
        )
        for block in blocks
        if block.get("block_type") == "narration"
        and isinstance(block.get("block_id"), int)
        and isinstance(block.get("text"), str)
    )
