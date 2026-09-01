from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from novel_core.style_analysis.model_contracts import JsonObject

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class AnalyzerResult(Generic[T]):  # noqa: UP046
    items: tuple[T, ...]
    warnings: tuple[str, ...] = ()
    partial: bool = False


def split_blocks(
    blocks: list[JsonObject], *, max_code_points: int = 15_000
) -> list[list[JsonObject]]:
    chunks: list[list[JsonObject]] = []
    current: list[JsonObject] = []
    current_size = 0
    for block in blocks:
        text = block.get("text")
        size = len(text) if isinstance(text, str) else 0
        if current and current_size + size > max_code_points:
            chunks.append(current)
            overlap = current[-2:] if len(current) >= 2 else current[:]
            current = [dict(item) for item in overlap]
            current_size = sum(len(str(item.get("text", ""))) for item in current)
        current.append(block)
        current_size += size
    if current:
        chunks.append(current)
    return chunks or [[]]
