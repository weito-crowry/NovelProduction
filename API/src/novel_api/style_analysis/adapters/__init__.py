from __future__ import annotations

from novel_api.style_analysis.adapters.base import (
    SourceAdapter,
    SourceType,
    UnsupportedSourceTypeError,
)
from novel_api.style_analysis.adapters.epub import EpubSourceAdapter
from novel_api.style_analysis.adapters.html_file import HtmlFileSourceAdapter
from novel_api.style_analysis.adapters.text import TextSourceAdapter

_ADAPTERS: dict[SourceType, SourceAdapter] = {
    "text": TextSourceAdapter(),
    "html_file": HtmlFileSourceAdapter(),
    "epub": EpubSourceAdapter(),
}


def get_source_adapter(source_type: str) -> SourceAdapter:
    try:
        return _ADAPTERS[source_type]  # type: ignore[index]
    except KeyError as exc:
        raise UnsupportedSourceTypeError(source_type) from exc


__all__ = ["get_source_adapter"]
