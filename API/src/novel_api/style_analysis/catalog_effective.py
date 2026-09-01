from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator


def _mapping_value(output: dict[str, object]) -> dict[str, object]:
    value = output.get("value")
    return dict(cast(dict[str, object], value)) if isinstance(value, dict) else {}


def effective_outputs(
    catalog: Any,
    outputs: Sequence[dict[str, object]],
    *,
    mentions: Sequence[dict[str, object]] = (),
    terms: Sequence[dict[str, object]] = (),
    structure_revision_id: int | None = None,
) -> dict[str, list[dict[str, object]]]:
    mention_resolutions = {
        output.get("subject_id"): output
        for output in outputs
        if output.get("annotation_type") == "mention.entity_resolution"
    }
    effective_terms: dict[object, dict[str, object]] = {}
    effective_mentions: list[dict[str, object]] = []
    for mention in mentions:
        item = dict(mention)
        resolution = mention_resolutions.get(mention.get("id"))
        if resolution is None:
            item["value"] = None
            item["entity_id"] = None
            item["source"] = "unknown"
        else:
            value = _mapping_value(resolution)
            entity_id = value.get("entity_id")
            item["value"] = value
            item["entity_id"] = entity_id
            item["source"] = "inferred" if isinstance(entity_id, int) else "unknown"
        effective_mentions.append(item)
    for term in terms:
        term_id = term.get("id")
        item = dict(term)
        item["novelty"] = "uncertain"
        item["value"] = {"value": "uncertain"}
        item["source"] = "default"
        effective_terms[term_id] = item
    effective: dict[str, list[dict[str, object]]] = {
        "mentions": effective_mentions,
        "terms": list(effective_terms.values()),
        "term_novelty": [],
        "speakers": [],
        "explanations": [],
        "scenes": [],
        "scene_axes": [],
        "pov": [],
        "blocks": [],
    }
    policy = DocumentAnalysisOrchestrator(
        catalog._connection,
        model_client=None,
    ).policy
    for output in outputs:
        item = dict(output)
        annotation_type = output.get("annotation_type")
        confidence = output.get("confidence")
        confidence_value = (
            float(confidence)
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
            else None
        )
        if annotation_type == "speaker":
            value = _mapping_value(output)
            if (
                value.get("reason_code") == "turn_taking"
                or confidence_value is None
                or confidence_value < policy.speaker_effective
            ):
                value["speaker_entity_id"] = None
                item["source"] = "unknown"
            else:
                item["source"] = "inferred"
            item["value"] = value
            effective["speakers"].append(item)
            continue
        if annotation_type in {"scene.function", "scene.tone"}:
            value = _mapping_value(output)
            labels = value.get("labels")
            accepted: list[object] = []
            if isinstance(labels, list):
                for label in labels:
                    if not isinstance(label, dict):
                        continue
                    label_name = label.get("label")
                    label_confidence = label.get("confidence", confidence_value)
                    if label_name == "unclear":
                        continue
                    if (
                        isinstance(label_confidence, (int, float))
                        and not isinstance(label_confidence, bool)
                        and label_confidence >= policy.scene_label_effective
                    ):
                        accepted.append(dict(label))
            value["labels"] = accepted or [
                {"label": "unclear", "confidence": confidence_value}
            ]
            item["value"] = value
            item["source"] = "inferred"
            effective["scenes"].append(item)
            effective["scene_axes"].append(item)
            continue
        if annotation_type in {
            "scene.pace",
            "scene.information_load",
            "scene.interaction",
        }:
            value = _mapping_value(output)
            if (
                confidence_value is None
                or confidence_value < policy.scene_label_effective
            ):
                value["label"] = "unclear"
            item["value"] = value
            item["source"] = "inferred"
            effective["scenes"].append(item)
            effective["scene_axes"].append(item)
            continue
        if annotation_type == "scene.pov":
            value = _mapping_value(output)
            if confidence_value is None or confidence_value < policy.pov_effective:
                value["pov_mode"] = "unclear"
                value["pov_entity_id"] = None
            item["value"] = value
            item["source"] = "inferred"
            effective["scenes"].append(item)
            effective["pov"].append(item)
            continue
        if annotation_type == "block.semantic_primary":
            value = _mapping_value(output)
            if (
                confidence_value is None
                or confidence_value < policy.block_semantic_effective
            ):
                value["label"] = "unclear"
            item["value"] = value
            item["source"] = "inferred"
            effective["blocks"].append(item)
            continue
        if annotation_type == "mention.entity_resolution":
            continue
        if annotation_type == "term.novelty":
            item = dict(effective_terms.get(output.get("subject_id"), output))
            value = _mapping_value(output)
            novelty = value.get("value")
            item["value"] = value
            item["novelty"] = novelty if isinstance(novelty, str) else "uncertain"
            item["source"] = "inferred"
            effective_terms[output.get("subject_id")] = item
            effective["term_novelty"].append(item)
            continue
        if annotation_type == "term_explanation":
            if (
                confidence_value is None
                or confidence_value < policy.term_explanation_effective
            ):
                item["value"] = None
            item["source"] = "inferred"
            effective["explanations"].append(item)

    effective["terms"] = list(effective_terms.values())
    if structure_revision_id is not None:
        append_unknown_effective_values(catalog, effective, structure_revision_id)
    return effective


def append_unknown_effective_values(
    catalog: Any,
    effective: dict[str, list[dict[str, object]]],
    structure_revision_id: int,
) -> None:
    scenes = catalog._connection.execute(
        "SELECT id FROM style_scenes WHERE structure_revision_id = ? ORDER BY id",
        (structure_revision_id,),
    ).fetchall()
    scene_axes = (
        "scene.function",
        "scene.tone",
        "scene.pace",
        "scene.information_load",
        "scene.interaction",
    )
    existing_scene_axes = {
        (item.get("annotation_type"), item.get("subject_id"))
        for item in effective["scene_axes"]
    }
    for (scene_id,) in scenes:
        for annotation_type in scene_axes:
            if (annotation_type, scene_id) in existing_scene_axes:
                continue
            unknown = {
                "annotation_type": annotation_type,
                "subject_type": "scene",
                "subject_id": scene_id,
                "value": None,
                "confidence": None,
                "analysis_run_id": None,
                "source": "unknown",
            }
            effective["scenes"].append(unknown)
            effective["scene_axes"].append(unknown)
        if not any(item.get("subject_id") == scene_id for item in effective["pov"]):
            effective["pov"].append(
                {
                    "annotation_type": "scene.pov",
                    "subject_type": "scene",
                    "subject_id": scene_id,
                    "value": None,
                    "confidence": None,
                    "analysis_run_id": None,
                    "source": "unknown",
                }
            )
    blocks = catalog._connection.execute(
        "SELECT id, block_type FROM style_blocks "
        "WHERE structure_revision_id = ? ORDER BY id",
        (structure_revision_id,),
    ).fetchall()
    existing_blocks = {item.get("subject_id") for item in effective["blocks"]}
    for block_id, block_type in blocks:
        if block_type == "narration" and block_id not in existing_blocks:
            effective["blocks"].append(
                {
                    "annotation_type": "block.semantic_primary",
                    "subject_type": "block",
                    "subject_id": block_id,
                    "value": None,
                    "confidence": None,
                    "analysis_run_id": None,
                    "source": "unknown",
                }
            )
