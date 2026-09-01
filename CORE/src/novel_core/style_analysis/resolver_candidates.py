from __future__ import annotations

import difflib
import unicodedata
from collections.abc import Mapping, Sequence
from typing import TypeAlias

BlockObject: TypeAlias = dict[str, object]  # noqa: UP040


def build_context_window(
    blocks: Sequence[Mapping[str, object]],
    *,
    subject_block_id: int,
    before: int,
    after: int,
) -> tuple[list[BlockObject], BlockObject, list[BlockObject]]:
    subject_index = next(
        (
            index
            for index, block in enumerate(blocks)
            if block.get("block_id") == subject_block_id
        ),
        None,
    )
    if subject_index is None:
        raise ValueError("SUBJECT_BLOCK_NOT_FOUND")
    subject = dict(blocks[subject_index])
    scene_id = subject.get("scene_id")
    same_scene = [
        dict(block)
        for block in blocks
        if block.get("scene_id") == scene_id and block.get("scene_id") is not None
    ]
    local_index = next(
        index
        for index, block in enumerate(same_scene)
        if block.get("block_id") == subject_block_id
    )
    previous = same_scene[max(0, local_index - before) : local_index]
    following = same_scene[local_index + 1 : local_index + 1 + after]
    return previous, subject, following


def comparison_key(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFC", value).casefold()
        if not char.isspace()
    )


def candidate_score(surface: str, candidate_values: Sequence[str]) -> float:
    source = comparison_key(surface)
    if not source:
        return 0.0
    return max(
        (
            difflib.SequenceMatcher(None, source, comparison_key(value)).ratio()
            for value in candidate_values
        ),
        default=0.0,
    )


def build_identity_shortlist(
    *,
    surface: str,
    canonical_name: str = "",
    candidate_type: str,
    identities: Sequence[Mapping[str, object]],
    same_scene_ids: set[int] | frozenset[int] = frozenset(),
    id_key: str = "entity_id",
    type_key: str = "entity_type",
    name_key: str = "canonical_name",
    aliases_key: str = "aliases",
) -> list[BlockObject]:
    result: list[tuple[int, float, int, BlockObject]] = []
    for identity in identities:
        identity_id = identity.get(id_key)
        if (
            isinstance(identity_id, bool)
            or not isinstance(identity_id, int)
            or identity_id <= 0
        ):
            continue
        if identity.get("enabled", True) is False:
            continue
        identity_type = identity.get(type_key)
        if candidate_type != "other" and identity_type != candidate_type:
            continue
        name = identity.get(name_key)
        aliases = identity.get(aliases_key, ())
        values = [name] if isinstance(name, str) else []
        if isinstance(aliases, Sequence) and not isinstance(aliases, (str, bytes)):
            values.extend(alias for alias in aliases if isinstance(alias, str))
        row = dict(identity)
        row["same_scene"] = identity_id in same_scene_ids
        score = max(
            candidate_score(surface, values),
            candidate_score(canonical_name, values),
        )
        result.append(
            (-(1 if identity_id in same_scene_ids else 0), -score, identity_id, row)
        )
    result.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in result[:20]]


def reduce_duplicate_items(
    items: Sequence[Mapping[str, object]],
    *,
    key_fields: tuple[str, ...],
    confidence_key: str = "confidence",
) -> list[BlockObject]:
    best: dict[tuple[object, ...], BlockObject] = {}
    for item in items:
        key = tuple(item.get(field) for field in key_fields)
        candidate = dict(item)
        current = best.get(key)
        candidate_confidence = candidate.get(confidence_key, 0.0)
        current_confidence = current.get(confidence_key, 0.0) if current else 0.0
        candidate_number = (
            float(candidate_confidence)
            if isinstance(candidate_confidence, (int, float))
            and not isinstance(candidate_confidence, bool)
            else 0.0
        )
        current_number = (
            float(current_confidence)
            if isinstance(current_confidence, (int, float))
            and not isinstance(current_confidence, bool)
            else 0.0
        )
        if current is None or candidate_number > current_number:
            best[key] = candidate
    return [best[key] for key in sorted(best, key=repr)]
