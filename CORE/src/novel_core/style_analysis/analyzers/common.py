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
    core_chunks: list[tuple[int, int, list[JsonObject]]] = []
    current: list[JsonObject] = []
    current_size = 0
    core_start = 0
    for index, block in enumerate(blocks):
        text = block.get("text")
        size = len(text) if isinstance(text, str) else 0
        if current and current_size + size > max_code_points:
            core_chunks.append((core_start, index, current))
            core_start = index
            current = []
            current_size = 0
        current.append(block)
        current_size += size
    if current:
        core_chunks.append((core_start, len(blocks), current))
    chunks: list[list[JsonObject]] = []
    for start, end, _core in core_chunks:
        context_start = max(0, start - 2)
        context_end = min(len(blocks), end + 2)
        chunks.append([dict(block) for block in blocks[context_start:context_end]])
    return chunks or [[]]
