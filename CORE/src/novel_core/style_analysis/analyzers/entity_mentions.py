from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from novel_core.style_analysis.analyzers.common import AnalyzerResult, split_blocks
from novel_core.style_analysis.entity_models import ENTITY_TYPES, MENTION_TYPES
from novel_core.style_analysis.model_contracts import (
    JsonObject,
    ModelClient,
    ModelRequest,
    complete_validated_json,
    require_int,
    validate_block_item,
    validate_confidence,
    validate_enum,
    validate_model_object,
    validate_positive_id,
)
from novel_core.style_analysis.model_prompts import get_prompt


@dataclass(frozen=True, slots=True)
class EntityMentionCandidate:
    block_id: int
    surface: str
    start_in_block: int
    end_in_block: int
    mention_type: str
    entity_type_candidate: str
    canonical_name_candidate: str
    confidence: float


def extract_entity_mentions(
    *,
    scene_id: int,
    blocks: Sequence[JsonObject],
    previous_context_blocks: Sequence[JsonObject],
    client: ModelClient,
) -> AnalyzerResult[EntityMentionCandidate]:
    prompt = get_prompt("style.entity_mentions")
    all_items: list[Mapping[str, object]] = []
    warnings: list[str] = []
    for chunk_index, chunk in enumerate(
        split_blocks([dict(block) for block in blocks])
    ):
        response = complete_validated_json(
            client,
            ModelRequest(
                prompt_id=prompt.prompt_id,
                prompt_version=prompt.version,
                system_prompt=prompt.system_prompt,
                user_payload={
                    "scene_id": scene_id,
                    "previous_context_blocks": [
                        dict(block) for block in previous_context_blocks
                    ]
                    if chunk_index == 0
                    else [],
                    "blocks": chunk,
                },
            ),
            _validate_response_shape,
        )
        result = response
        mentions = result["mentions"]
        if not isinstance(mentions, list):
            raise ValueError("MODEL_CONTRACT_INVALID")
        block_texts = {
            block_id: text
            for block in chunk
            if isinstance(block_id := block.get("block_id"), int)
            and isinstance(text := block.get("text"), str)
        }
        for item in mentions:
            try:
                obj = validate_block_item(
                    item,
                    block_texts=block_texts,
                    required=(
                        "block_id",
                        "surface",
                        "start_in_block",
                        "end_in_block",
                        "mention_type",
                        "entity_type_candidate",
                        "canonical_name_candidate",
                        "confidence",
                    ),
                    allowed=(
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
                block_id = validate_positive_id(obj["block_id"])
                assert block_id is not None
                mention_type = validate_enum(
                    obj["mention_type"], MENTION_TYPES, code="MENTION_TYPE"
                )
                entity_type = validate_enum(
                    obj["entity_type_candidate"], ENTITY_TYPES, code="ENTITY_TYPE"
                )
                surface = obj["surface"]
                canonical = obj["canonical_name_candidate"]
                if (
                    not isinstance(surface, str)
                    or not isinstance(canonical, str)
                    or not canonical
                ):
                    raise ValueError("MODEL_ITEM_INVALID")
                start = obj["start_in_block"]
                end = obj["end_in_block"]
                confidence = validate_confidence(obj["confidence"])
                if not isinstance(start, int) or not isinstance(end, int):
                    raise ValueError("MODEL_ITEM_SPAN_INVALID")
                all_items.append(
                    {
                        "block_id": block_id,
                        "surface": surface,
                        "start_in_block": start,
                        "end_in_block": end,
                        "mention_type": mention_type,
                        "entity_type_candidate": entity_type,
                        "canonical_name_candidate": canonical,
                        "confidence": confidence,
                    }
                )
            except ValueError as exc:
                warnings.append(str(exc))
    dedup: dict[tuple[object, ...], Mapping[str, object]] = {}
    for item in all_items:
        key = (
            item["block_id"],
            item["start_in_block"],
            item["end_in_block"],
            item["mention_type"],
        )
        current = dedup.get(key)
        if current is None or validate_confidence(
            item["confidence"]
        ) > validate_confidence(current["confidence"]):
            dedup[key] = item
    items = tuple(
        EntityMentionCandidate(
            block_id=require_int(item["block_id"]),
            surface=str(item["surface"]),
            start_in_block=require_int(item["start_in_block"]),
            end_in_block=require_int(item["end_in_block"]),
            mention_type=str(item["mention_type"]),
            entity_type_candidate=str(item["entity_type_candidate"]),
            canonical_name_candidate=str(item["canonical_name_candidate"]),
            confidence=validate_confidence(item["confidence"]),
        )
        for item in sorted(
            dedup.values(),
            key=lambda value: (
                require_int(value["block_id"]),
                require_int(value["start_in_block"]),
                require_int(value["end_in_block"]),
                str(value["mention_type"]),
            ),
        )
    )
    return AnalyzerResult(items, tuple(warnings), bool(warnings))


def _validate_response_shape(value: JsonObject) -> JsonObject:
    result = validate_model_object(value, required=("mentions",), allowed=("mentions",))
    if not isinstance(result["mentions"], list):
        raise ValueError("MODEL_CONTRACT_INVALID")
    return result
