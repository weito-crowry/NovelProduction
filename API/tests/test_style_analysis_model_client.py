from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from novel_core.style_analysis.model_contracts import ModelRequest

from novel_api.config import ApiSettings
from novel_api.style_analysis.model_client import (
    OpenAICompatibleModelClient,
)


def test_openai_compatible_client_uses_minimal_chat_contract_without_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok":true}'}}]}
        )

    client = OpenAICompatibleModelClient(
        base_url="http://local/v1/",
        model_id="style-model",
        transport=httpx.MockTransport(handler),
    )
    assert client.complete_json(
        ModelRequest("style.test", 1, "system", {"b": 2, "a": "日本語"})
    ) == {"ok": True}
    request = seen[0]
    assert request.url == "http://local/v1/chat/completions"
    assert "authorization" not in request.headers
    body = request.content
    assert b'"temperature":0.0' in body
    assert b'"model":"style-model"' in body


def test_openai_compatible_client_repairs_invalid_json_once() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "not-json" if calls == 1 else '{"repaired":true}'
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    client = OpenAICompatibleModelClient(
        base_url="http://local/v1",
        model_id="style-model",
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )
    assert client.complete_json(ModelRequest("style.test", 1, "system", {})) == {
        "repaired": True
    }
    assert calls == 2


def test_api_settings_validates_style_provider() -> None:
    with pytest.raises(ValueError, match="ANALYZER_PROVIDER_UNAVAILABLE"):
        ApiSettings(data_root=Path("."), style_model_provider="openai_compatible")
