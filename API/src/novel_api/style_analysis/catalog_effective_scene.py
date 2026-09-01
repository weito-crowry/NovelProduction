from __future__ import annotations

import json
from typing import Any

from novel_core.style_analysis.runtime_models import AnalysisPolicy
from novel_core.style_analysis.semantic_metric_support import (
    EffectiveValue,
    latest_override,
)
from novel_core.style_analysis.semantic_scene import resolve_scene_semantics


def as_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def output_with_effective(
    output: dict[str, object] | None,
    *,
    annotation_type: str,
    subject_type: str,
    subject_id: int,
    result: EffectiveValue,
    value: object,
) -> dict[str, object]:
    item = dict(output or {})
    item.update(
        {
            "annotation_type": annotation_type,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "value": value,
            "confidence": result.confidence
            if result.confidence is not None
            else item.get("confidence"),
            "analysis_run_id": result.analysis_run_id
            if result.analysis_run_id is not None
            else item.get("analysis_run_id"),
            "source": result.source,
        }
    )
    if result.override_id is not None:
        item["override_id"] = result.override_id
    if result.stale_override:
        item["stale_override"] = True
    return item


def effective_scene_output(
    connection: Any,
    output: dict[str, object],
    policy: AnalysisPolicy,
    structure_revision_id: int,
) -> dict[str, object]:
    annotation_type = str(output["annotation_type"])
    scene_id = as_int(output.get("subject_id"))
    raw_annotations = {
        annotation_type: (
            json.dumps(output.get("value"), ensure_ascii=False, sort_keys=True),
            output.get("confidence"),
            output.get("start_cp"),
        )
    }
    result = resolve_scene_semantics(
        connection,
        scene_id,
        as_int(output.get("analysis_run_id")),
        raw_annotations,
        structure_revision_id=structure_revision_id,
        scene_threshold=policy.scene_label_effective,
        pov_threshold=policy.pov_effective,
    )[annotation_type]
    item = output_with_effective(
        output,
        annotation_type=annotation_type,
        subject_type="scene",
        subject_id=scene_id,
        result=result,
        value=result.value,
    )
    return item


def active_override(
    connection: Any, subject_type: str, subject_id: int, field_path: str
) -> tuple[int, str, str | None, int | None] | None:
    row = latest_override(connection, subject_type, subject_id, field_path)
    if row is None:
        return None
    full = connection.execute(
        "SELECT id, operation, value_json, structure_revision_id "
        "FROM style_manual_overrides WHERE id=?",
        (row[0],),
    ).fetchone()
    return None if full is None else (int(full[0]), str(full[1]), full[2], full[3])


def override_is_stale(
    connection: Any,
    subject_type: str,
    subject_id: int,
    field_path: str,
    structure_revision_id: int,
) -> bool:
    override = active_override(connection, subject_type, subject_id, field_path)
    return (
        override is not None
        and override[3] is not None
        and int(override[3]) != structure_revision_id
    )


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
            synthetic = {
                "annotation_type": annotation_type,
                "subject_type": "scene",
                "subject_id": scene_id,
                "value": None,
                "confidence": None,
                "analysis_run_id": None,
            }
            if active_override(catalog._connection, "scene", scene_id, annotation_type):
                value = effective_scene_output(
                    catalog._connection,
                    synthetic,
                    AnalysisPolicy(),
                    structure_revision_id,
                )
            else:
                value = {**synthetic, "source": "unknown"}
            effective["scenes"].append(value)
            effective["scene_axes"].append(value)
        if not any(item.get("subject_id") == scene_id for item in effective["pov"]):
            synthetic_pov = {
                "annotation_type": "scene.pov",
                "subject_type": "scene",
                "subject_id": scene_id,
                "value": None,
                "confidence": None,
                "analysis_run_id": None,
            }
            has_pov_override = active_override(
                catalog._connection, "scene", scene_id, "scene.pov_mode"
            ) or active_override(
                catalog._connection, "scene", scene_id, "scene.pov_entity_id"
            )
            if has_pov_override:
                pov = effective_scene_output(
                    catalog._connection,
                    synthetic_pov,
                    AnalysisPolicy(),
                    structure_revision_id,
                )
            else:
                pov = {**synthetic_pov, "source": "unknown"}
            effective["pov"].append(pov)
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
