from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765


@dataclass(frozen=True, slots=True)
class ApiSettings:
    data_root: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    dev_cors_origin: str | None = None
    webui_dist: Path | None = None
    style_model_provider: str = "disabled"
    style_model_base_url: str | None = None
    style_model_id: str | None = None
    style_model_api_key: str | None = None
    style_model_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.style_model_provider not in {"disabled", "openai_compatible"}:
            raise ValueError("STYLE_MODEL_PROVIDER_INVALID")
        if self.style_model_provider == "openai_compatible":
            if not self.style_model_base_url or not self.style_model_id:
                raise ValueError("ANALYZER_PROVIDER_UNAVAILABLE")
        if (
            not math.isfinite(self.style_model_timeout_seconds)
            or not 1.0 <= self.style_model_timeout_seconds <= 300.0
        ):
            raise ValueError("STYLE_MODEL_TIMEOUT_INVALID")
        if self.style_model_base_url is not None:
            base_url = self.style_model_base_url.rstrip("/")
            if not base_url:
                raise ValueError("STYLE_MODEL_BASE_URL_INVALID")
            object.__setattr__(self, "style_model_base_url", base_url)


def _source_checkout_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_data_root() -> Path:
    checkout_root = _source_checkout_root()
    if (checkout_root / "CORE").is_dir() and (checkout_root / "MCP").is_dir():
        return checkout_root / "data"
    return Path.cwd() / "data"


def resolve_data_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit

    env_data_root = os.getenv("NOVEL_DATA_ROOT")
    if env_data_root:
        return Path(env_data_root)

    return _default_data_root()
