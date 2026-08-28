from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from novel_api.app import create_app
from novel_api.config import ApiSettings


@pytest.mark.anyio
async def test_health_is_api_only_and_does_not_require_project(
    tmp_path: Path,
) -> None:
    app = create_app(ApiSettings(data_root=tmp_path))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "v1"}
