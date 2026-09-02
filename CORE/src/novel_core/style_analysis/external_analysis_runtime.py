from __future__ import annotations

import sqlite3
from dataclasses import asdict

from novel_core.style_analysis.analysis_repository import AnalysisRunRepository
from novel_core.style_analysis.current_run_resolver import CurrentRunResolver
from novel_core.style_analysis.fingerprints import JsonObject, fingerprint_json
from novel_core.style_analysis.metrics import (
    BASIC_METRIC_DEFINITIONS,
    SEMANTIC_METRIC_DEFINITIONS,
)
from novel_core.style_analysis.model_output_contracts import RESPONSE_CONTRACT_IDS
from novel_core.style_analysis.model_prompts import PROMPT_REGISTRY
from novel_core.style_analysis.runtime_models import AnalysisPolicy
from novel_core.style_analysis.runtime_registry import ANALYZERS

ENGINE_CONTRACT_VERSION = 1
CHUNKING_CONTRACT_VERSION = 1
CURRENT_CHUNK_MAX_CODE_POINTS = 15_000


def analysis_policy_json(policy: AnalysisPolicy) -> JsonObject:
    return {key: value for key, value in asdict(policy).items()}


def external_analysis_runtime_contract() -> JsonObject:
    return {
        "engine_contract_version": ENGINE_CONTRACT_VERSION,
        "analysis_policy_contract_version": AnalysisPolicy().version,
        "analyzers": {item.id: item.version for item in ANALYZERS},
        "prompts": dict(PROMPT_REGISTRY),
        "response_contracts": list(RESPONSE_CONTRACT_IDS),
        "scene_taxonomy_version": 1,
        "block_semantic_taxonomy_version": 1,
        "pov_taxonomy_version": 1,
        "metric_versions": {
            **{
                name: definition.version
                for name, definition in BASIC_METRIC_DEFINITIONS.items()
            },
            **{
                name: definition.version
                for name, definition in SEMANTIC_METRIC_DEFINITIONS.items()
            },
        },
        "structure_segmenter": {
            "id": "canonical-fiction-structure",
            "version": 1,
        },
        "model_chunking_contract_version": CHUNKING_CONTRACT_VERSION,
        "current_chunk_max_code_points": CURRENT_CHUNK_MAX_CODE_POINTS,
    }


def external_analysis_runtime_contract_fingerprint() -> str:
    return fingerprint_json(external_analysis_runtime_contract())


def current_analysis_input_fingerprints(
    connection: sqlite3.Connection, policy: AnalysisPolicy, run_id: int
) -> tuple[str | None, str | None]:
    """Recompute relevant run inputs using the canonical resolver."""
    runs = AnalysisRunRepository(connection)
    run = runs.get_run(run_id)
    if run is None:
        return None, None
    resolver = CurrentRunResolver(connection, policy)
    dependencies = tuple(
        dependency
        for _analyzer_id, dependency_id in run.dependency_runs
        if (dependency := runs.get_run(dependency_id)) is not None
    )
    _config, state_fingerprint, policy_fingerprint = resolver._inputs(
        run.document_id,
        run.text_revision_id,
        run.structure_revision_id,
        run.analyzer_id,
        dependencies,
    )
    return state_fingerprint, policy_fingerprint
