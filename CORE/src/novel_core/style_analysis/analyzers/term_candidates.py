from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from novel_core.style_analysis.analyzers.common import AnalyzerResult, split_blocks
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
)
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.term_models import NOVELTY_VALUES, TERM_TYPES


@dataclass(frozen=True, slots=True)
class TermCandidate:
    block_id: int
    surface: str
    start_in_block: int
    end_in_block: int
    canonical_label_candidate: str
    term_type_candidate: str
    novelty_candidate: str
    confidence: float


def extract_term_candidates(
    *, scene_id: int, blocks: Sequence[JsonObject], client: ModelClient
) -> AnalyzerResult[TermCandidate]:
    prompt = get_prompt("style.term_candidates")
    valid: list[Mapping[str, object]] = []
    warnings: list[str] = []
    for chunk in split_blocks([dict(block) for block in blocks]):
        response = complete_validated_json(
            client,
            ModelRequest(
                prompt_id=prompt.prompt_id,
                prompt_version=prompt.version,
                system_prompt=prompt.system_prompt,
                user_payload={"scene_id": scene_id, "blocks": chunk},
            ),
            _validate_response_shape,
        )
        obj = response
        terms = obj["terms"]
        if not isinstance(terms, list):
            raise ValueError("MODEL_CONTRACT_INVALID")
        texts = {
            require_int(block["block_id"]): str(block["text"])
            for block in chunk
            if isinstance(block.get("block_id"), int)
            and isinstance(block.get("text"), str)
        }
        for item in terms:
            try:
                candidate = validate_block_item(
                    item,
                    block_texts=texts,
                    required=(
                        "block_id",
                        "surface",
                        "start_in_block",
                        "end_in_block",
                        "canonical_label_candidate",
                        "term_type_candidate",
                        "novelty_candidate",
                        "confidence",
                    ),
                    allowed=(
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
                validate_enum(
                    candidate["term_type_candidate"], TERM_TYPES, code="TERM_TYPE"
                )
                validate_enum(
                    candidate["novelty_candidate"], NOVELTY_VALUES, code="NOVELTY"
                )
                validate_confidence(candidate["confidence"])
                if (
                    not isinstance(candidate["canonical_label_candidate"], str)
                    or not candidate["canonical_label_candidate"]
                ):
                    raise ValueError("MODEL_ITEM_INVALID")
                valid.append(candidate)
            except ValueError as exc:
                warnings.append(str(exc))
    dedup: dict[tuple[object, ...], Mapping[str, object]] = {}
    for item in valid:
        key = (item["block_id"], item["start_in_block"], item["end_in_block"])
        old = dedup.get(key)
        if old is None or validate_confidence(item["confidence"]) > validate_confidence(
            old["confidence"]
        ):
            dedup[key] = item
    result = tuple(
        TermCandidate(
            block_id=require_int(item["block_id"]),
            surface=str(item["surface"]),
            start_in_block=require_int(item["start_in_block"]),
            end_in_block=require_int(item["end_in_block"]),
            canonical_label_candidate=str(item["canonical_label_candidate"]),
            term_type_candidate=str(item["term_type_candidate"]),
            novelty_candidate=str(item["novelty_candidate"]),
            confidence=validate_confidence(item["confidence"]),
        )
        for item in sorted(
            dedup.values(),
            key=lambda value: (
                require_int(value["block_id"]),
                require_int(value["start_in_block"]),
                require_int(value["end_in_block"]),
            ),
        )
    )
    return AnalyzerResult(result, tuple(warnings), bool(warnings))


def _validate_response_shape(value: JsonObject) -> JsonObject:
    obj = validate_model_object(value, required=("terms",), allowed=("terms",))
    if not isinstance(obj["terms"], list):
        raise ValueError("MODEL_CONTRACT_INVALID")
    return obj
