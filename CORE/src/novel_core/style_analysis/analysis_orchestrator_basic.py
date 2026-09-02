from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from novel_core.style_analysis.fingerprints import JsonObject
from novel_core.style_analysis.metrics import (
    BASIC_METRIC_DEFINITIONS,
    calculate_basic_metrics,
)
from novel_core.style_analysis.structure_models import (
    BlockRecord,
    SceneRecord,
    SentenceRecord,
)


class BasicMetricsMixin:
    _new_run: Any
    _finish: Any
    measurements: Any

    def _basic(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        text: str,
        scenes: Sequence[SceneRecord],
        blocks: Sequence[BlockRecord],
        sentences: Sequence[SentenceRecord],
    ) -> tuple[int, list[JsonObject]]:
        run_id = self._new_run(
            "style-metrics-basic",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            config={
                "metric_versions": {
                    name: definition.version
                    for name, definition in sorted(BASIC_METRIC_DEFINITIONS.items())
                }
            },
        )
        try:
            measurements = calculate_basic_metrics(
                document_id=document_id,
                canonical_text=text,
                scenes=tuple(scenes),
                blocks=tuple(blocks),
                sentences=tuple(sentences),
            )
            values: list[JsonObject] = [
                {
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "metric_name": item.metric_name,
                    "metric_version": item.metric_version,
                    "value": item.value,
                    "sample_count": item.sample_count,
                }
                for item in measurements
            ]
            for item in measurements:
                definition = BASIC_METRIC_DEFINITIONS[item.metric_name]
                self.measurements.insert(
                    analysis_run_id=run_id,
                    structure_revision_id=structure_id,
                    target_type=item.target_type,
                    target_id=item.target_id,
                    metric_name=item.metric_name,
                    metric_version=item.metric_version,
                    value=item.value,
                    value_type=definition.value_type,
                    sample_count=item.sample_count,
                )
            self._finish(run_id)
            return run_id, values
        except Exception as exc:
            self._finish(run_id, status="failed", error=exc)
            raise
