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

SPEAKER_REASONS = frozenset(
    {
        "explicit_speech_tag",
        "adjacent_action",
        "turn_taking",
        "addressed_name",
        "scene_context",
        "unknown",
    }
)


@dataclass(frozen=True, slots=True)
class SpeakerAttribution:
    speaker_entity_id: int | None
    confidence: float
    evidence_block_ids: tuple[int, ...]
    reason_code: str


def attribute_speaker(
    *,
    previous_blocks: Sequence[JsonObject],
    subject_block: JsonObject,
    next_blocks: Sequence[JsonObject],
    people: Sequence[JsonObject],
    client: ModelClient,
) -> SpeakerAttribution:
    if subject_block.get("block_type") != "dialogue":
        raise ValueError("DIALOGUE_BLOCK_REQUIRED")
    prompt = get_prompt("style.speaker_attribution")
    response = client.complete_json(
        ModelRequest(
            prompt.prompt_id,
            prompt.version,
            prompt.system_prompt,
            {
                "previous_blocks": list(previous_blocks),
                "subject_block": subject_block,
                "next_blocks": list(next_blocks),
                "people": list(people),
            },
        )
    )
    obj = validate_model_object(
        response,
        required=(
            "speaker_entity_id",
            "confidence",
            "evidence_block_ids",
            "reason_code",
        ),
        allowed=(
            "speaker_entity_id",
            "confidence",
            "evidence_block_ids",
            "reason_code",
        ),
    )
    speaker_id = validate_positive_id(obj["speaker_entity_id"], nullable=True)
    people_ids = {
        require_int(person["entity_id"])
        for person in people
        if isinstance(person.get("entity_id"), int)
        and not isinstance(person.get("entity_id"), bool)
    }
    if speaker_id is not None and speaker_id not in people_ids:
        raise ValueError("MODEL_ITEM_ID_INVALID")
    evidence = obj["evidence_block_ids"]
    allowed_evidence = {
        require_int(block["block_id"])
        for block in [*previous_blocks, subject_block, *next_blocks]
        if isinstance(block.get("block_id"), int)
    }
    if not isinstance(evidence, list) or any(
        not isinstance(item, int)
        or isinstance(item, bool)
        or item not in allowed_evidence
        for item in evidence
    ):
        raise ValueError("MODEL_ITEM_ID_INVALID")
    reason = obj["reason_code"]
    if reason not in SPEAKER_REASONS:
        raise ValueError("MODEL_ITEM_ENUM_INVALID")
    return SpeakerAttribution(
        speaker_id,
        validate_confidence(obj["confidence"]),
        tuple(sorted({require_int(item) for item in evidence})),
        str(reason),
    )
