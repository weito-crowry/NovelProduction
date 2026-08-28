from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

ProjectStatus = Literal["active", "archived"]
MetadataState = Literal["ok", "missing", "invalid"]
ProjectHealth = Literal["ok", "degraded"]
_UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", re.ASCII)


def validate_utc_timestamp(value: str) -> str:
    if _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError("timestamp must be UTC ISO-8601")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("timestamp must be UTC ISO-8601") from exc
    return value


class ProjectMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    status: ProjectStatus
    created_at: str
    updated_at: str

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return validate_utc_timestamp(value)


class ProjectSummary(BaseModel):
    project_id: str
    status: ProjectStatus
    metadata_state: MetadataState
    working_title: str | None
    created_at: str | None
    updated_at: str | None
    health: ProjectHealth


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_title: str
    project_id: str | None = None

    @field_validator("working_title")
    @classmethod
    def validate_working_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("working_title must be non-empty")
        return value


class ProjectStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProjectStatus
