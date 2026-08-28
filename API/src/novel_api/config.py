from __future__ import annotations

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
