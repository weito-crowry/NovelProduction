from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok", "api_version": "v1"}
