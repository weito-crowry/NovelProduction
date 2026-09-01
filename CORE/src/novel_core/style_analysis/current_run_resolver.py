from __future__ import annotations

import json
import sqlite3
from typing import cast

from novel_core.style_analysis.analysis_orchestrator import (
    DocumentAnalysisOrchestrator,
)
from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.analysis_runtime import AnalysisRuntime
from novel_core.style_analysis.fingerprints import JsonValue, fingerprint_json
from novel_core.style_analysis.metrics import (
    BASIC_METRIC_DEFINITIONS,
    SEMANTIC_METRIC_DEFINITIONS,
)
from novel_core.style_analysis.model_prompts import get_prompt
from novel_core.style_analysis.runtime_models import (
    AnalysisPolicy,
    AnalysisRunRecord,
    DependencyRunExpectation,
)
from novel_core.style_analysis.runtime_registry import ANALYZERS_BY_ID
from novel_core.style_analysis.term_prefix import TermPrefixEntry

_PROMPTS = {
    "entity-mention-extractor": "style.entity_mentions",
    "entity-resolver": "style.entity_resolution",
    "speaker-attribution": "style.speaker_attribution",
    "term-candidate-extractor": "style.term_candidates",
    "term-resolver": "style.term_resolution",
    "term-explanation-detector": "style.term_explanation",
    "scene-semantic-classifier": "style.scene_semantics",
    "block-semantic-classifier": "style.block_semantic",
    "pov-classifier": "style.pov",
}


class CurrentRunResolver:
    """Resolve a run through the same dependency contract used at execution."""

    def __init__(
        self, connection: sqlite3.Connection, policy: AnalysisPolicy | None = None
    ) -> None:
        self.connection = connection
        self.policy = policy or AnalysisPolicy()
        self.runs = AnalysisRunRepository(connection)
        self.runtime = AnalysisRuntime(self.runs)
        self.state = DocumentAnalysisOrchestrator(
            connection, model_client=None, policy=self.policy
        )
        self._cache: dict[tuple[int, int, int, str], AnalysisRunRecord | None] = {}

    def clear(self) -> None:
        self._cache.clear()

    def resolve(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        analyzer_id: str,
    ) -> AnalysisRunRecord | None:
        key = (document_id, text_revision_id, structure_id, analyzer_id)
        if key in self._cache:
            return self._cache[key]
        self._cache[key] = None
        definition = ANALYZERS_BY_ID.get(analyzer_id)
        if definition is None:
            return None
        dependencies = self._dependencies(
            document_id, text_revision_id, structure_id, analyzer_id
        )
        if dependencies is None:
            return None
        config, state_fingerprint, policy_fingerprint = self._inputs(
            document_id,
            text_revision_id,
            structure_id,
            analyzer_id,
            dependencies,
        )
        prompt_id, prompt_version = self._prompt(analyzer_id)
        result = self.runtime.resolve_current_run(
            document_id=document_id,
            analyzer_id=analyzer_id,
            text_revision_id=text_revision_id,
            structure_revision_id=structure_id,
            analyzer_version=definition.version,
            config_json=json.dumps(
                config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            state_fingerprint=state_fingerprint,
            policy_input_fingerprint=policy_fingerprint,
            dependency_runs=tuple((run.analyzer_id, run.id) for run in dependencies),
            dependency_expectations=tuple(
                self._expectation(run) for run in dependencies
            ),
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
        self._cache[key] = result
        return result

    def term_prefix(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        current_term_run_id: int | None = None,
    ) -> tuple[tuple[TermPrefixEntry, ...], bool]:
        row = self.connection.execute(
            "SELECT re.id, re.reference_work_id, re.order_index "
            "FROM style_documents sd JOIN style_reference_episodes re "
            "ON re.id = sd.reference_episode_id WHERE sd.id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return (
                (
                    TermPrefixEntry(
                        0,
                        0,
                        document_id,
                        text_revision_id,
                        structure_id,
                        current_term_run_id or 0,
                    ),
                )
                if current_term_run_id is not None
                else (),
                current_term_run_id is not None,
            )
        work_id, target_order = int(row[1]), int(row[2])
        episodes = self.connection.execute(
            "SELECT re.id, re.order_index, sd.id, sd.current_text_revision_id, "
            "sd.current_structure_revision_id FROM style_reference_episodes re "
            "LEFT JOIN style_documents sd ON sd.reference_episode_id = re.id "
            "WHERE re.reference_work_id = ? AND re.order_index <= ? "
            "ORDER BY re.order_index, re.id",
            (work_id, target_order),
        ).fetchall()
        entries: list[TermPrefixEntry] = []
        complete = True
        for (
            episode_id,
            order,
            source_document,
            source_text,
            source_structure,
        ) in episodes:
            if (
                source_document is None
                or source_text is None
                or source_structure is None
            ):
                complete = False
                continue
            source_document_id = int(source_document)
            source_text_id = int(source_text)
            source_structure_id = int(source_structure)
            if source_document_id == document_id:
                run = (
                    self.runs.get_run(current_term_run_id)
                    if current_term_run_id is not None
                    else None
                )
                if (
                    run is None
                    or run.analyzer_id != "term-resolver"
                    or run.document_id != source_document_id
                    or run.text_revision_id != source_text_id
                    or run.structure_revision_id != source_structure_id
                ):
                    run = self.resolve(
                        source_document_id,
                        source_text_id,
                        source_structure_id,
                        "term-resolver",
                    )
            else:
                run = self.resolve(
                    source_document_id,
                    source_text_id,
                    source_structure_id,
                    "term-resolver",
                )
            if run is None:
                complete = False
                continue
            if run.status != "succeeded":
                complete = False
            entries.append(
                TermPrefixEntry(
                    int(episode_id),
                    int(order),
                    source_document_id,
                    source_text_id,
                    source_structure_id,
                    run.id,
                )
            )
        return tuple(entries), complete and bool(entries)

    def term_prefix_state(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        current_term_run_id: int | None = None,
    ) -> dict[str, JsonValue]:
        entries, complete = self.term_prefix(
            document_id, text_revision_id, structure_id, current_term_run_id
        )
        return {
            "complete": complete,
            "entries": [
                {
                    "episode_id": item.episode_id,
                    "episode_order": item.episode_order,
                    "document_id": item.document_id,
                    "text_revision_id": item.text_revision_id,
                    "structure_revision_id": item.structure_revision_id,
                    "term_resolver_run_id": item.term_run_id,
                }
                for item in entries
            ],
        }

    def _dependencies(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        analyzer_id: str,
    ) -> tuple[AnalysisRunRecord, ...] | None:
        definition = ANALYZERS_BY_ID[analyzer_id]
        result: list[AnalysisRunRecord] = []
        for dependency in definition.dependencies:
            run = self.resolve(
                document_id, text_revision_id, structure_id, dependency.analyzer_id
            )
            if run is None:
                return None
            result.append(run)
        return tuple(result)

    def _inputs(
        self,
        document_id: int,
        text_revision_id: int,
        structure_id: int,
        analyzer_id: str,
        dependencies: tuple[AnalysisRunRecord, ...],
    ) -> tuple[dict[str, JsonValue], str | None, str | None]:
        config: dict[str, JsonValue] = {}
        if analyzer_id == "style-metrics-basic":
            config = {
                "metric_versions": {
                    name: definition.version
                    for name, definition in sorted(BASIC_METRIC_DEFINITIONS.items())
                }
            }
        elif analyzer_id == "style-metrics-semantic":
            term_run = self._dependency(dependencies, "term-resolver")
            config = {
                "metric_versions": {
                    name: definition.version
                    for name, definition in sorted(SEMANTIC_METRIC_DEFINITIONS.items())
                }
            }
            prefix_state = self.term_prefix_state(
                document_id,
                text_revision_id,
                structure_id,
                term_run.id if term_run else None,
            )
            state = {
                "metric_effective_state": self.state._metric_effective_state(
                    document_id, structure_id
                ),
                "term_first_appearance": prefix_state,
            }
            return (
                config,
                fingerprint_json(cast(JsonValue, state)),
                self._policy_fingerprint(
                    (
                        "speaker_effective",
                        "term_explanation_effective",
                        "block_semantic_effective",
                    )
                ),
            )
        elif analyzer_id == "scene-semantic-classifier":
            config = {"scene_taxonomy_version": 1}
        elif analyzer_id == "block-semantic-classifier":
            config = {"block_semantic_taxonomy_version": 1}
        elif analyzer_id == "pov-classifier":
            entity = self._dependency(dependencies, "entity-resolver")
            state = {
                "mention_resolution": self.state._mention_resolution_state(
                    document_id, structure_id, entity.id if entity else 0
                )
            }
            return config, fingerprint_json(cast(JsonValue, state)), None
        if analyzer_id == "entity-resolver":
            state = {
                "scope": self.state.entities._scope(document_id),
                "entity_registry_state": self.state._entity_registry_state(document_id),
            }
            return (
                config,
                fingerprint_json(cast(JsonValue, state)),
                self._policy_fingerprint(("entity_resolution_auto_merge",)),
            )
        if analyzer_id == "speaker-attribution":
            entity = self._dependency(dependencies, "entity-resolver")
            state = {
                "mention_resolution": self.state._mention_resolution_state(
                    document_id, structure_id, entity.id if entity else 0
                )
            }
            return config, fingerprint_json(cast(JsonValue, state)), None
        if analyzer_id == "term-resolver":
            state = {
                "scope": self.state.terms._scope(document_id),
                "term_registry_state": self.state._term_registry_state(document_id),
            }
            return (
                config,
                fingerprint_json(cast(JsonValue, state)),
                self._policy_fingerprint(("term_resolution_auto_merge",)),
            )
        return config, None, None

    def _policy_fingerprint(self, keys: tuple[str, ...]) -> str:
        return fingerprint_json(cast(JsonValue, self.policy.input_values(keys)))

    @staticmethod
    def _dependency(
        dependencies: tuple[AnalysisRunRecord, ...], analyzer_id: str
    ) -> AnalysisRunRecord | None:
        return next(
            (run for run in dependencies if run.analyzer_id == analyzer_id), None
        )

    @staticmethod
    def _expectation(run: AnalysisRunRecord) -> DependencyRunExpectation:
        return DependencyRunExpectation(
            analyzer_id=run.analyzer_id,
            run_id=run.id,
            config_json=run.config_json,
            state_fingerprint=run.state_fingerprint,
            policy_input_fingerprint=run.policy_input_fingerprint,
            prompt_id=run.prompt_id,
            prompt_version=run.prompt_version,
        )

    @staticmethod
    def _prompt(analyzer_id: str) -> tuple[str | None, int | None]:
        prompt_id = _PROMPTS.get(analyzer_id)
        if prompt_id is None:
            return None, None
        prompt = get_prompt(prompt_id)
        return prompt.prompt_id, prompt.version
