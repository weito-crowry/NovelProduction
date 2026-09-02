from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, cast

import httpx
from novel_core.style_analysis.fingerprints import JsonValue, canonical_json_bytes
from novel_core.style_analysis.model_contracts import (
    REPAIR_SYSTEM_PROMPT,
    JsonObject,
    ModelRequest,
)

from novel_api.config import ApiSettings


class ModelClientError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


class OpenAICompatibleModelClient:
    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport
        self._sleep = sleep

    def complete_json(self, request: ModelRequest) -> JsonObject:
        content = self._complete_content(request)
        try:
            return self._parse_object(content)
        except ModelClientError as first_error:
            return self._repair(
                request,
                content=content,
                validation_errors=[first_error.code],
            )

    def complete_json_validated(
        self,
        request: ModelRequest,
        validator: Callable[[JsonObject], JsonObject],
    ) -> JsonObject:
        content = self._complete_content(request)
        try:
            return validator(self._parse_object(content))
        except ModelClientError as first_error:
            if first_error.code != "MODEL_RESPONSE_INVALID":
                raise
            return self._repair(
                request,
                content=content,
                validation_errors=[first_error.code],
                validator=validator,
            )
        except ValueError as first_error:
            return self._repair(
                request,
                content=content,
                validation_errors=[str(first_error)],
                validator=validator,
            )

    def _repair(
        self,
        request: ModelRequest,
        *,
        content: str,
        validation_errors: list[str],
        validator: Callable[[JsonObject], JsonObject] | None = None,
    ) -> JsonObject:
        repair_request = ModelRequest(
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            system_prompt=REPAIR_SYSTEM_PROMPT,
            user_payload={
                "original_request": request.user_payload,
                "invalid_response": content,
                "validation_errors": validation_errors,
            },
        )
        try:
            repaired = self._parse_object(self._complete_content(repair_request))
            return validator(repaired) if validator is not None else repaired
        except (ModelClientError, ValueError) as second_error:
            raise ModelClientError(
                "MODEL_CONTRACT_INVALID", str(second_error)
            ) from second_error

    def _complete_content(self, request: ModelRequest) -> str:
        payload = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {
                    "role": "user",
                    "content": canonical_json_bytes(
                        cast(JsonValue, request.user_payload)
                    ).decode("utf-8"),
                },
            ],
            "temperature": 0.0,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        for attempt in range(2):
            try:
                with httpx.Client(
                    transport=self._transport, timeout=self._timeout
                ) as client:
                    response = client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    self._sleep(1.0)
                    continue
                raise ModelClientError("MODEL_TIMEOUT") from exc
            except httpx.HTTPError as exc:
                raise ModelClientError("MODEL_HTTP_ERROR") from exc
            if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                self._sleep(1.0)
                continue
            if response.status_code >= 400:
                raise ModelClientError("MODEL_HTTP_ERROR", str(response.status_code))
            try:
                response_json = response.json()
                content = response_json["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise ModelClientError("MODEL_RESPONSE_INVALID") from exc
            if not isinstance(content, str):
                raise ModelClientError("MODEL_RESPONSE_INVALID")
            return content
        raise ModelClientError("MODEL_HTTP_ERROR")

    @staticmethod
    def _parse_object(content: str) -> JsonObject:
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelClientError("MODEL_RESPONSE_INVALID") from exc
        if not isinstance(value, dict):
            raise ModelClientError("MODEL_RESPONSE_INVALID")
        return dict(value)


def build_model_client(settings: ApiSettings) -> OpenAICompatibleModelClient | None:
    if settings.style_model_provider == "disabled":
        return None
    return OpenAICompatibleModelClient(
        base_url=settings.style_model_base_url or "",
        model_id=settings.style_model_id or "",
        api_key=settings.style_model_api_key,
        timeout_seconds=settings.style_model_timeout_seconds,
    )
