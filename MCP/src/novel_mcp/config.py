import os
from dataclasses import dataclass

DEFAULT_API_URL = "http://127.0.0.1:8765"


@dataclass(frozen=True, slots=True)
class McpSettings:
    api_url: str
    connect_timeout_seconds: float = 2.0
    request_timeout_seconds: float = 30.0


def resolve_settings(api_url: str | None = None) -> McpSettings:
    selected = api_url or os.environ.get("NOVEL_API_URL") or DEFAULT_API_URL
    return McpSettings(selected.rstrip("/"))
