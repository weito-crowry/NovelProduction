from __future__ import annotations

from collections.abc import Sequence

from novel_core.style_analysis.analyzers.common import split_blocks
from novel_core.style_analysis.model_contracts import (
    JsonObject,
    ModelClient,
    ModelRequest,
    validate_confidence,
    validate_enum,
    validate_model_object,
)
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.semantic_models import (
    SCENE_FUNCTIONS,
    SCENE_INFORMATION_LOADS,
    SCENE_INTERACTIONS,
    SCENE_PACES,
    SCENE_TONES,
)


def classify_scene(
    *, scene_id: int, blocks: Sequence[JsonObject], client: ModelClient
) -> JsonObject:
    prompt = get_prompt("style.scene_semantics")
    chunks = split_blocks([dict(block) for block in blocks])
    responses: list[JsonObject] = []
    for chunk in chunks:
        response = client.complete_json(
            ModelRequest(
                prompt.prompt_id,
                prompt.version,
                prompt.system_prompt,
                {"mode": "classify", "scene_id": scene_id, "blocks": chunk},
            )
        )
        responses.append(_validate_scene_response(response, allow_reduce=False))
    if len(responses) == 1:
        return responses[0]
    functions = _reduce_labels(responses, "function")
    tones = _reduce_labels(responses, "tone")
    reduce_response = client.complete_json(
        ModelRequest(
            prompt.prompt_id,
            prompt.version,
            prompt.system_prompt,
            {
                "mode": "reduce",
                "chunks": [
                    {
                        "char_count": sum(
                            len(str(block.get("text", ""))) for block in chunk
                        ),
                        "pace": result["pace"],
                        "information_load": result["information_load"],
                        "interaction": result["interaction"],
                    }
                    for chunk, result in zip(chunks, responses, strict=False)
                ],
            },
        )
    )
    reduced = _validate_scene_response(reduce_response, allow_reduce=True)
    return {
        "function": functions,
        "tone": tones,
        "pace": reduced["pace"],
        "information_load": reduced["information_load"],
        "interaction": reduced["interaction"],
    }


def _validate_scene_response(value: object, *, allow_reduce: bool) -> JsonObject:
    required = (
        ("pace", "information_load", "interaction")
        if allow_reduce
        else ("function", "tone", "pace", "information_load", "interaction")
    )
    obj = validate_model_object(
        value,
        required=required,
        allowed=("function", "tone", "pace", "information_load", "interaction"),
    )
    if not allow_reduce:
        for key, choices in (("function", SCENE_FUNCTIONS), ("tone", SCENE_TONES)):
            values = obj[key]
            if not isinstance(values, list):
                raise ValueError("MODEL_CONTRACT_INVALID")
            seen: set[str] = set()
            for entry in values:
                item = validate_model_object(
                    entry,
                    required=("label", "confidence"),
                    allowed=("label", "confidence"),
                )
                label = validate_enum(item["label"], choices, code="SEMANTIC_LABEL")
                if label in seen:
                    continue
                validate_confidence(item["confidence"])
                seen.add(label)
            if not values:
                raise ValueError("MODEL_CONTRACT_INVALID")
    for key, choices in (
        ("pace", SCENE_PACES),
        ("information_load", SCENE_INFORMATION_LOADS),
        ("interaction", SCENE_INTERACTIONS),
    ):
        axis_value = obj[key]
        if not isinstance(axis_value, dict):
            raise ValueError("MODEL_CONTRACT_INVALID")
        axis_item = validate_model_object(
            axis_value,
            required=("label", "confidence"),
            allowed=("label", "confidence"),
        )
        validate_enum(axis_item["label"], choices, code="SEMANTIC_LABEL")
        validate_confidence(axis_item["confidence"])
    return obj


def _reduce_labels(responses: Sequence[JsonObject], key: str) -> list[JsonObject]:
    best: dict[str, JsonObject] = {}
    for response in responses:
        values = response[key]
        assert isinstance(values, list)
        for value in values:
            assert isinstance(value, dict)
            label = str(value["label"])
            old = best.get(label)
            if old is None or validate_confidence(
                value["confidence"]
            ) > validate_confidence(old["confidence"]):
                best[label] = dict(value)
    concrete = [item for label, item in best.items() if label != "unclear"]
    values = concrete if concrete else [best["unclear"]] if "unclear" in best else []
    return sorted(values, key=lambda item: str(item["label"]))
