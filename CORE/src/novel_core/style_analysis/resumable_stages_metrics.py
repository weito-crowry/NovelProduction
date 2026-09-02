from __future__ import annotations

from typing import Any

from novel_core.style_analysis.metrics import (
    BASIC_METRIC_DEFINITIONS,
    METRIC_DEFINITIONS,
    calculate_basic_metrics,
)
from novel_core.style_analysis.resumable_models import ResumableStageHost
from novel_core.style_analysis.semantic_metrics import calculate_semantic_metrics


class ResumableMetricsStagesMixin(ResumableStageHost):
    @staticmethod
    def _measurement_values(measurements: Any) -> list[dict[str, object]]:
        return [
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

    def _finish_noop_stage(self, state: dict[str, Any], analyzer_id: str) -> None:
        run_id = self._ensure_run(state, analyzer_id, None)
        if state.pop("stage_reused", False):
            casted = self._measurement_values(self.measurements.list_for_run(run_id))
            state.setdefault("metrics", []).extend(casted)
            self._next_stage(state)
            return
        if self._dependency_failed(state, analyzer_id):
            self.runs.finish_run(
                run_id,
                status="failed",
                error_code="DEPENDENCY_FAILED",
                error_message="DEPENDENCY_FAILED",
            )
            self._next_stage(state)
            return
        document_id = int(state["document_id"])
        structure_id = int(state["structure_revision_id"])
        text_revision_id = int(state["text_revision_id"])
        revision = self.text.get_text_revision(document_id, text_revision_id)
        scenes = tuple(self.structure.list_scenes(structure_id))
        blocks = tuple(self.structure.list_blocks(structure_id))
        if analyzer_id == "style-metrics-basic":
            measurements = calculate_basic_metrics(
                document_id=document_id,
                canonical_text=revision.canonical_text,
                scenes=scenes,
                blocks=blocks,
                sentences=tuple(self.structure.list_sentences(structure_id)),
            )
            state.setdefault("metrics", []).extend(
                self._measurement_values(measurements)
            )
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
        else:
            dependency_analyzers = (
                "speaker-attribution",
                "term-resolver",
                "term-explanation-detector",
                "block-semantic-classifier",
            )
            by_analyzer = {
                analyzer_id: dependency_run_id
                for analyzer_id in dependency_analyzers
                if (dependency_run_id := self._dependency_run_id(state, analyzer_id))
            }
            result = calculate_semantic_metrics(
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
            )
            state.setdefault("metrics", []).extend(
                self._measurement_values(result.measurements)
            )
            for item in result.measurements:
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
        if analyzer_id == "style-metrics-semantic" and not state.get("metrics"):
            self.runs.finish_run(
                run_id,
                status="failed",
                finished_at=None,
                error_code="SEMANTIC_METRICS_EMPTY",
                error_message="SEMANTIC_METRICS_EMPTY",
            )
        else:
            self._finish_run(run_id)
        self._next_stage(state)
