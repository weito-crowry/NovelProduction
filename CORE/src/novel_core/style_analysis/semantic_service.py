from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import cast

from novel_core.style_analysis.semantic_models import (
    BLOCK_PRIMARY_LABELS,
    POV_MODES,
    SCENE_FUNCTIONS,
    SCENE_INFORMATION_LOADS,
    SCENE_INTERACTIONS,
    SCENE_PACES,
    SCENE_TONES,
)
from novel_core.style_analysis.semantic_repository import SemanticRepository


class SemanticService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.repository = SemanticRepository(connection)

    def insert_raw(
        self,
        *,
        annotation_type: str,
        subject_type: str,
        subject_id: int,
        value: object,
        confidence: float | None,
        analysis_run_id: int,
        start_cp: int | None = None,
        end_cp: int | None = None,
    ) -> None:
        self.repository.insert_annotation(
            annotation_type=annotation_type,
            subject_type=subject_type,
            subject_id=subject_id,
            value_json=json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            confidence=confidence,
            analysis_run_id=analysis_run_id,
            start_cp=start_cp,
            end_cp=end_cp,
        )

    @staticmethod
    def validate_axis(axis: str, labels: Sequence[str]) -> None:
        choices = {
            "function": SCENE_FUNCTIONS,
            "tone": SCENE_TONES,
            "pace": SCENE_PACES,
            "information_load": SCENE_INFORMATION_LOADS,
            "interaction": SCENE_INTERACTIONS,
            "block": BLOCK_PRIMARY_LABELS,
            "pov": POV_MODES,
        }.get(axis)
        if (
            choices is None
            or not labels
            or any(label not in choices for label in labels)
        ):
            raise ValueError("SEMANTIC_LABEL_INVALID")
        if "unclear" in labels and len(set(labels)) != 1:
            raise ValueError("SEMANTIC_UNCLEAR_CONFLICT")

    def effective_single(
        self,
        *,
        analysis_run_id: int,
        subject_type: str,
        subject_id: int,
        threshold: float,
    ) -> tuple[str | None, str]:
        row = self._connection.execute(
            "SELECT value_json, confidence FROM style_annotations "
            "WHERE analysis_run_id = ? AND subject_type = ? AND subject_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (analysis_run_id, subject_type, subject_id),
        ).fetchone()
        if row is None:
            return None, "unknown"
        value = json.loads(cast(str, row[0]))
        label = value.get("label") if isinstance(value, dict) else None
        confidence = row[1]
        if not isinstance(label, str):
            return None, "unknown"
        if (
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and confidence >= threshold
        ):
            return label, "inferred"
        return "unclear", "inferred"
