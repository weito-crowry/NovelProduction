from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

from novel_core.style_analysis.analysis_orchestrator import DocumentAnalysisOrchestrator
from novel_core.style_analysis.runtime_models import AnalysisPolicy
from novel_core.style_analysis.semantic_metric_support import (
    resolve_block_semantic,
    resolve_entity_enabled,
    resolve_entity_name,
    resolve_entity_type,
    resolve_mention_entity,
    resolve_speaker,
    resolve_term_enabled,
    resolve_term_label,
    resolve_term_mention_explanation,
    resolve_term_novelty,
    resolve_term_type,
)

from novel_api.style_analysis.catalog_effective_scene import (
    append_unknown_effective_values,
)
from novel_api.style_analysis.catalog_effective_scene import (
    as_int as _as_int,
)
from novel_api.style_analysis.catalog_effective_scene import (
    effective_scene_output as _effective_scene_output,
)
from novel_api.style_analysis.catalog_effective_scene import (
    output_with_effective as _output_with_effective,
)
from novel_api.style_analysis.catalog_effective_scene import (
    override_is_stale as _override_is_stale,
)


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
    term_resolver_run_ids: Sequence[int] = (),
) -> dict[str, list[dict[str, object]]]:
    if structure_revision_id is not None and _has_semantic_tables(catalog):
        return _database_effective_outputs(
            catalog,
            outputs,
            mentions=mentions,
            terms=terms,
            structure_revision_id=structure_revision_id,
            term_resolver_run_ids=term_resolver_run_ids,
        )
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


def _has_semantic_tables(catalog: Any) -> bool:
    row = catalog._connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='style_manual_overrides'"
    ).fetchone()
    return row is not None


def _raw_tuple(output: dict[str, object] | None) -> tuple[str, object, object] | None:
    if output is None:
        return None
    return (
        json.dumps(output.get("value"), ensure_ascii=False, sort_keys=True),
        output.get("confidence"),
        output.get("start_cp"),
    )


def _database_effective_outputs(
    catalog: Any,
    outputs: Sequence[dict[str, object]],
    *,
    mentions: Sequence[dict[str, object]],
    terms: Sequence[dict[str, object]],
    structure_revision_id: int,
    term_resolver_run_ids: Sequence[int],
) -> dict[str, list[dict[str, object]]]:
    connection = catalog._connection
    policy = AnalysisPolicy()
    by_annotation = {
        (str(item.get("annotation_type")), _as_int(item.get("subject_id"))): item
        for item in outputs
        if isinstance(item.get("subject_id"), int)
    }
    effective_mentions: list[dict[str, object]] = []
    for mention in mentions:
        mention_id = _as_int(mention.get("id"))
        raw_output = by_annotation.get(("mention.entity_resolution", mention_id))
        run_id = _as_int(raw_output.get("analysis_run_id")) if raw_output else 0
        stale = _override_is_stale(
            connection,
            "mention",
            mention_id,
            "mention.entity_id",
            structure_revision_id,
        )
        result = resolve_mention_entity(
            connection,
            mention_id,
            run_id,
            _raw_tuple(raw_output),
            include_manual=not stale,
        )
        result = replace(result, stale_override=stale)
        entity_id = result.value if isinstance(result.value, int) else None
        value = {"entity_id": entity_id} if entity_id is not None else None
        item = dict(mention)
        item.update(
            {
                "value": value,
                "entity_id": entity_id,
                "source": result.source,
                "override_id": result.override_id,
                "stale_override": result.stale_override,
            }
        )
        effective_mentions.append(item)

    effective_entities: list[dict[str, object]] = []
    for entity in catalog._entities_for_document(
        int(
            connection.execute(
                "SELECT document_id FROM style_structure_revisions sr "
                "JOIN style_text_revisions tr ON tr.id=sr.text_revision_id "
                "WHERE sr.id=?",
                (structure_revision_id,),
            ).fetchone()[0]
        )
    ):
        entity_id = _as_int(entity.get("id"))
        item = dict(entity)
        item["canonical_name"] = resolve_entity_name(connection, entity_id).value
        item["entity_type"] = resolve_entity_type(connection, entity_id).value
        item["enabled"] = resolve_entity_enabled(connection, entity_id).value
        effective_entities.append(item)

    effective_terms: list[dict[str, object]] = []
    effective_term_novelty: list[dict[str, object]] = []
    for term in terms:
        term_id = _as_int(term.get("id"))
        raw_output = by_annotation.get(("term.novelty", term_id))
        run_id = _as_int(raw_output.get("analysis_run_id")) if raw_output else 0
        raw = (
            (
                term_id,
                json.dumps(raw_output.get("value"), ensure_ascii=False),
                raw_output.get("confidence"),
                None,
            )
            if raw_output is not None
            else None
        )
        stale = _override_is_stale(
            connection, "term", term_id, "term.novelty", structure_revision_id
        )
        result = resolve_term_novelty(
            connection, term_id, run_id, raw, include_manual=not stale
        )
        result = replace(result, stale_override=stale)
        item = dict(term)
        item.update(
            {
                "canonical_label": resolve_term_label(connection, term_id).value,
                "term_type": resolve_term_type(connection, term_id).value,
                "enabled": resolve_term_enabled(connection, term_id).value,
                "novelty": result.value
                if isinstance(result.value, str)
                else "uncertain",
                "value": {"value": result.value}
                if isinstance(result.value, str)
                else {"value": "uncertain"},
                "source": result.source,
            }
        )
        effective_terms.append(item)
        if raw_output is not None or result.source != "default":
            effective_term_novelty.append(item)

    effective: dict[str, list[dict[str, object]]] = {
        "entities": effective_entities,
        "mentions": effective_mentions,
        "terms": effective_terms,
        "term_novelty": effective_term_novelty,
        "speakers": [],
        "explanations": [],
        "scenes": [],
        "scene_axes": [],
        "pov": [],
        "blocks": [],
    }
    for output in outputs:
        annotation_type = output.get("annotation_type")
        subject_id = output.get("subject_id")
        if not isinstance(subject_id, int):
            continue
        if annotation_type == "speaker":
            stale = _override_is_stale(
                connection,
                "block",
                subject_id,
                "block.speaker_entity_id",
                structure_revision_id,
            )
            result = resolve_speaker(
                connection,
                subject_id,
                _as_int(output.get("analysis_run_id")),
                _raw_tuple(output),
                policy.speaker_effective,
                include_manual=not stale,
            )
            result = replace(result, stale_override=stale)
            speaker_value = _mapping_value(output)
            speaker_value["speaker_entity_id"] = (
                result.value if isinstance(result.value, int) else None
            )
            effective["speakers"].append(
                _output_with_effective(
                    output,
                    annotation_type="speaker",
                    subject_type="block",
                    subject_id=subject_id,
                    result=result,
                    value=speaker_value,
                )
            )
        elif annotation_type == "block.semantic_primary":
            stale = _override_is_stale(
                connection,
                "block",
                subject_id,
                "block.semantic_primary",
                structure_revision_id,
            )
            result = resolve_block_semantic(
                connection,
                subject_id,
                _as_int(output.get("analysis_run_id")),
                _raw_tuple(output),
                policy.block_semantic_effective,
                include_manual=not stale,
            )
            result = replace(result, stale_override=stale)
            block_value = _mapping_value(output)
            block_value["label"] = result.value
            effective["blocks"].append(
                _output_with_effective(
                    output,
                    annotation_type="block.semantic_primary",
                    subject_type="block",
                    subject_id=subject_id,
                    result=result,
                    value=block_value,
                )
            )
        elif annotation_type == "term_explanation":
            stale = _override_is_stale(
                connection,
                "term_mention",
                subject_id,
                "term_mention.sufficient_explanation_annotation_id",
                structure_revision_id,
            )
            result = resolve_term_mention_explanation(
                connection,
                subject_id,
                _as_int(output.get("analysis_run_id")),
                policy.term_explanation_effective,
                include_manual=not stale,
            )
            result = replace(result, stale_override=stale)
            effective["explanations"].append(
                _output_with_effective(
                    output,
                    annotation_type="term_explanation",
                    subject_type="term_mention",
                    subject_id=subject_id,
                    result=result,
                    value=result.value,
                )
            )
        elif isinstance(annotation_type, str) and annotation_type.startswith("scene."):
            item = _effective_scene_output(
                connection, output, policy, structure_revision_id
            )
            effective["scenes"].append(item)
            effective["scene_axes"].append(item)
            if annotation_type == "scene.pov":
                effective["pov"].append(item)

    if structure_revision_id is not None:
        append_unknown_effective_values(
            catalog,
            effective,
            structure_revision_id,
            term_resolver_run_ids=term_resolver_run_ids,
        )
    return effective
