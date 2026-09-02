from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from novel_core.style_analysis.fingerprints import fingerprint_json
from novel_core.style_analysis.model_contracts import REPAIR_SYSTEM_PROMPT
from novel_core.style_analysis.model_output_contracts import (
    RESPONSE_CONTRACT_IDS,
    ResponseContractRegistry,
    task_request_fingerprint,
)
from novel_core.style_analysis.resumable_models import (
    CompletedModelCall,
    EngineAdvanceResult,
    PreparedModelCall,
)


def _prepared() -> PreparedModelCall:
    return PreparedModelCall(
        call_key="scene:1:chunk:0",
        analysis_run_id=7,
        analyzer_id="scene-semantic-classifier",
        analyzer_version=1,
        prompt_id="style.scene_semantics",
        prompt_version=1,
        response_contract_id="style.scene_semantics.classify.v1",
        system_prompt="system",
        user_payload={"scene_id": 1, "blocks": []},
        response_schema={"type": "object"},
    )


def test_prepared_model_call_is_frozen_and_serializable() -> None:
    call = _prepared()

    with pytest.raises(FrozenInstanceError):
        call.call_key = "other"  # type: ignore[misc]
    assert call.user_payload["scene_id"] == 1


@pytest.mark.parametrize(
    ("response", "error_code", "error_message"),
    [
        ({"ok": True}, None, None),
        (None, "MODEL_HTTP_ERROR", "provider failed"),
    ],
)
def test_completed_model_call_accepts_exactly_one_completion_form(
    response: dict[str, object] | None,
    error_code: str | None,
    error_message: str | None,
) -> None:
    assert (
        CompletedModelCall(
            call_key="call",
            response=response,
            error_code=error_code,
            error_message=error_message,
        ).call_key
        == "call"
    )


@pytest.mark.parametrize(
    ("response", "error_code"),
    [({"ok": True}, "MODEL_HTTP_ERROR"), (None, None)],
)
def test_completed_model_call_rejects_ambiguous_completion(
    response: dict[str, object] | None, error_code: str | None
) -> None:
    with pytest.raises(ValueError, match="COMPLETED_MODEL_CALL_INVALID"):
        CompletedModelCall(
            call_key="call",
            response=response,
            error_code=error_code,
            error_message=None,
        )


def test_engine_advance_result_exposes_pending_or_terminal_result_only() -> None:
    with pytest.raises(ValueError, match="ENGINE_ADVANCE_RESULT_INVALID"):
        EngineAdvanceResult(cursor={"schema_version": 1})


def test_response_contract_registry_has_exact_eleven_ids() -> None:
    assert RESPONSE_CONTRACT_IDS == (
        "style.scene_boundary.v1",
        "style.entity_mentions.v1",
        "style.entity_resolution.v1",
        "style.speaker_attribution.v1",
        "style.term_candidates.v1",
        "style.term_resolution.v1",
        "style.term_explanation.v1",
        "style.scene_semantics.classify.v1",
        "style.scene_semantics.reduce.v1",
        "style.block_semantic.v1",
        "style.pov.v1",
    )
    assert all(
        ResponseContractRegistry.get(contract_id).validator
        for contract_id in RESPONSE_CONTRACT_IDS
    )


def test_task_request_fingerprint_uses_only_canonical_prepared_call_fields() -> None:
    call = _prepared()
    expected = fingerprint_json(
        {
            "call_key": call.call_key,
            "attempt_no": 1,
            "analyzer_id": call.analyzer_id,
            "analyzer_version": call.analyzer_version,
            "prompt_id": call.prompt_id,
            "prompt_version": call.prompt_version,
            "response_contract_id": call.response_contract_id,
            "system_prompt": call.system_prompt,
            "user_payload": call.user_payload,
            "response_schema": call.response_schema,
        }
    )
    assert task_request_fingerprint(call, attempt_no=1) == expected


def test_repair_prompt_is_single_core_authority() -> None:
    assert ResponseContractRegistry.repair_system_prompt() is REPAIR_SYSTEM_PROMPT
