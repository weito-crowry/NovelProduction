from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ProjectEnvelope(BaseModel, Generic[T]):  # noqa: UP046 - required public contract
    project_id: str
    data: T


class ApiError(BaseModel):
    code: str
    message: str
    project_id: str | None
    details: dict[str, Any]


class ErrorEnvelope(BaseModel):
    error: ApiError
