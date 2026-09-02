from __future__ import annotations

from collections.abc import Sequence

from novel_core.style_analysis.analyzers.common import split_blocks
from novel_core.style_analysis.model_contracts import (
    JsonObject,
    ModelClient,
    ModelRequest,
    complete_validated_json,
    require_int,
    validate_confidence,
    validate_enum,
    validate_model_object,
    validate_positive_id,
)
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.semantic_models import POV_MODES


def classify_pov(
    *,
    scene_id: int,
    blocks: Sequence[JsonObject],
    people: Sequence[JsonObject],
    client: ModelClient,
) -> JsonObject:
    prompt = get_prompt("style.pov")
    chunks = split_blocks([dict(block) for block in blocks])
    values: list[JsonObject] = []
    for chunk in chunks:
        response = complete_validated_json(
            client,
            ModelRequest(
                prompt.prompt_id,
                prompt.version,
                prompt.system_prompt,
                {
                    "mode": "classify",
                    "scene_id": scene_id,
                    "blocks": chunk,
                    "people": list(people),
                },
            ),
            lambda value: _validate(value, people),
        )
        values.append(response)
    if len(values) == 1:
        return values[0]
    response = complete_validated_json(
        client,
        ModelRequest(
            prompt.prompt_id,
            prompt.version,
            prompt.system_prompt,
            {
                "mode": "reduce",
                "people": list(people),
                "chunks": [
                    {
                        "char_count": sum(
                            len(str(block.get("text", ""))) for block in chunk
                        ),
                        **value,
                    }
                    for chunk, value in zip(chunks, values, strict=False)
                ],
            },
        ),
        lambda value: _validate(value, people),
    )
    return _validate(response, people)


def validate_pov_response(value: object, people: Sequence[JsonObject]) -> JsonObject:
    obj = validate_model_object(
        value,
        required=("pov_mode", "pov_entity_id", "confidence"),
        allowed=("pov_mode", "pov_entity_id", "confidence"),
    )
    validate_enum(obj["pov_mode"], POV_MODES, code="POV_MODE")
    entity_id = validate_positive_id(obj["pov_entity_id"], nullable=True)
    people_ids = {
        require_int(person["entity_id"])
        for person in people
        if isinstance(person.get("entity_id"), int)
        and not isinstance(person.get("entity_id"), bool)
    }
    if entity_id is not None and entity_id not in people_ids:
        raise ValueError("MODEL_ITEM_ID_INVALID")
    validate_confidence(obj["confidence"])
    return obj


def _validate(value: object, people: Sequence[JsonObject]) -> JsonObject:
    return validate_pov_response(value, people)
