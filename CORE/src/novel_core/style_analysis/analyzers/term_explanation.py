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
    validate_span,
)
from novel_core.style_analysis.model_prompts import get_prompt


@dataclass(frozen=True, slots=True)
class TermExplanationCandidate:
    block_id: int
    start_in_block: int
    end_in_block: int
    explanation_kind: str
    completeness: str
    confidence: float


def detect_term_explanations(
    *,
    term_mention_id: int,
    term_label: str,
    mention_block_id: int,
    mention_start_in_block: int,
    mention_end_in_block: int,
    blocks: Sequence[JsonObject],
    client: ModelClient,
) -> tuple[TermExplanationCandidate, ...]:
    prompt = get_prompt("style.term_explanation")
    response = client.complete_json(
        ModelRequest(
            prompt.prompt_id,
            prompt.version,
            prompt.system_prompt,
            {
                "term_mention_id": term_mention_id,
                "term_label": term_label,
                "mention_block_id": mention_block_id,
                "mention_start_in_block": mention_start_in_block,
                "mention_end_in_block": mention_end_in_block,
                "blocks": list(blocks),
            },
        )
    )
    obj = validate_model_object(
        response, required=("explanations",), allowed=("explanations",)
    )
    values = obj["explanations"]
    if not isinstance(values, list):
        raise ValueError("MODEL_CONTRACT_INVALID")
    block_texts = {
        require_int(block["block_id"]): str(block["text"])
        for block in blocks
        if isinstance(block.get("block_id"), int) and isinstance(block.get("text"), str)
    }
    result: list[TermExplanationCandidate] = []
    for value in values:
        item = validate_model_object(
            value,
            required=(
                "block_id",
                "start_in_block",
                "end_in_block",
                "explanation_kind",
                "completeness",
                "confidence",
            ),
            allowed=(
                "block_id",
                "start_in_block",
                "end_in_block",
                "explanation_kind",
                "completeness",
                "confidence",
            ),
        )
        block_id = validate_positive_id(item["block_id"])
        assert block_id is not None
        text = block_texts.get(block_id)
        if text is None:
            raise ValueError("MODEL_ITEM_ID_INVALID")
        start = item["start_in_block"]
        end = item["end_in_block"]
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError("MODEL_ITEM_SPAN_INVALID")
        validate_span(text, start, end, text[start:end])
        kind = item["explanation_kind"]
        completeness = item["completeness"]
        if kind not in {
            "definition",
            "paraphrase",
            "example",
            "contextual_clue",
            "contrast",
            "other",
        } or completeness not in {"partial", "sufficient"}:
            raise ValueError("MODEL_ITEM_ENUM_INVALID")
        result.append(
            TermExplanationCandidate(
                block_id,
                start,
                end,
                str(kind),
                str(completeness),
                validate_confidence(item["confidence"]),
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                0 if item.completeness == "sufficient" else 1,
                -item.confidence,
                abs(item.start_in_block - mention_start_in_block),
                item.start_in_block,
                item.end_in_block,
            ),
        )
    )
