from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

ExternalSessionStatus: TypeAlias = Literal[  # noqa: UP040
    "active", "succeeded", "partial", "failed", "cancelled"
]
ExternalTaskStatus: TypeAlias = Literal[  # noqa: UP040
    "pending", "accepted", "repair_required", "rejected", "superseded"
]


@dataclass(frozen=True, slots=True)
class ExternalAnalysisSessionRecord:
    id: int
    document_id: int | None
    reference_work_id: int | None
    executor_provider: str
    executor_model_id: str
    runtime_contract_fingerprint: str
    status: ExternalSessionStatus
    request_json: str
    snapshot_json: str
    cursor_json: str
    result_json: str
    warning_json: str
    version: int
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class ExternalAnalysisTaskRecord:
    id: int
    session_id: int
    analysis_run_id: int
    sequence_no: int
    call_key: str
    analyzer_id: str
    analyzer_version: int
    prompt_id: str
    prompt_version: int
    response_contract_id: str
    attempt_no: int
    parent_task_id: int | None
    request_fingerprint: str
    request_json: str
    response_json: str | None
    response_fingerprint: str | None
    status: ExternalTaskStatus
    error_json: str
    version: int
    created_at: str
    updated_at: str
    submitted_at: str | None


@dataclass(frozen=True, slots=True)
class ExternalAnalysisSessionRunRecord:
    session_id: int
    run_id: int
    run_role: Literal["created", "reused"]
