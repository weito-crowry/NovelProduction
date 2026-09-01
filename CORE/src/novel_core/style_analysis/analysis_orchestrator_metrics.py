from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from novel_core.style_analysis.fingerprints import (
    JsonObject,
    JsonValue,
    fingerprint_json,
)
from novel_core.style_analysis.metrics import (
    METRIC_DEFINITIONS,
    SEMANTIC_METRIC_DEFINITIONS,
)
from novel_core.style_analysis.semantic_metrics import calculate_semantic_metrics
from novel_core.style_analysis.structure_models import BlockRecord, SceneRecord
from novel_core.style_analysis.text_models import TextRevisionRecord


class SemanticMetricsMixin:
    def _semantic_metrics(
        self: Any,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        revision: TextRevisionRecord,
        scenes: Sequence[SceneRecord],
        blocks: Sequence[BlockRecord],
        dependency_runs: Sequence[int],
    ) -> tuple[int, list[JsonObject]]:
        required_analyzers = (
            "speaker-attribution",
            "term-resolver",
            "term-explanation-detector",
            "block-semantic-classifier",
        )
        runs_by_analyzer = {
            self.runs.get_run(item).analyzer_id: item
            for item in dependency_runs
            if self.runs.get_run(item) is not None
        }
        required_runs = tuple(
            runs_by_analyzer[analyzer_id]
            for analyzer_id in required_analyzers
            if analyzer_id in runs_by_analyzer
        )
        term_run = self.runs.get_run(runs_by_analyzer.get("term-resolver", -1))
        run_id = self._new_run(
            "style-metrics-semantic",
            document_id=document_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            dependencies=required_runs,
            state_fingerprint=fingerprint_json(
                cast(
                    JsonValue,
                    {
                        "metric_effective_state": self._metric_effective_state(
                            document_id, structure_id
                        ),
                        "term_first_appearance": {
                            "document_id": document_id,
                            "text_revision_id": text_revision_id,
                            "structure_revision_id": structure_id,
                            "term_resolver_run_id": (
                                term_run.id if term_run is not None else None
                            ),
                            "resolver_status": (
                                term_run.status if term_run is not None else None
                            ),
                        },
                    },
                )
            ),
            policy_inputs=(
                "speaker_effective",
                "term_explanation_effective",
                "block_semantic_effective",
            ),
            config={
                "metric_versions": {
                    name: definition.version
                    for name, definition in sorted(SEMANTIC_METRIC_DEFINITIONS.items())
                }
            },
        )
        if self._is_reused(run_id):
            return run_id, []
        by_analyzer = {
            self.runs.get_run(item).analyzer_id: item
            for item in required_runs
            if self.runs.get_run(item) is not None
        }
        calculated = calculate_semantic_metrics(
            self.connection,
            document_id=document_id,
            canonical_text=revision.canonical_text,
            scenes=scenes,
            blocks=blocks,
            speaker_run_id=by_analyzer.get("speaker-attribution"),
            term_run_id=by_analyzer.get("term-resolver"),
            explanation_run_id=by_analyzer.get("term-explanation-detector"),
            block_run_id=by_analyzer.get("block-semantic-classifier"),
            speaker_threshold=self.policy.speaker_effective,
            block_threshold=self.policy.block_semantic_effective,
            term_explanation_threshold=self.policy.term_explanation_effective,
            term_first_appearance_complete=(
                term_run is not None and term_run.status == "succeeded"
            ),
        )
        values: list[JsonObject] = []
        for item in calculated.measurements:
            definition = METRIC_DEFINITIONS[item.metric_name]
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
            values.append(
                {
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "metric_name": item.metric_name,
                    "metric_version": item.metric_version,
                    "value": item.value,
                    "sample_count": item.sample_count,
                }
            )
        self._finish(
            run_id,
            status="partial" if calculated.partial else "succeeded",
        )
        return run_id, values
