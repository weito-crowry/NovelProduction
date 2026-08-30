"""Extensible Canonical Document export boundary."""

from __future__ import annotations

from dataclasses import dataclass

from ..model import NovelDocument


@dataclass(frozen=True, slots=True)
class ExportWarning:
    """A non-fatal target-format degradation."""

    code: str
    message: str
    block_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Common result returned by every document exporter."""

    format: str
    media_type: str
    content: str
    warnings: tuple[ExportWarning, ...] = ()
    suggested_filename: str | None = None


def export_document(document: NovelDocument, format: str) -> ExportResult:
    """Dispatch one Canonical Document to a supported export renderer."""

    if format == "narou":
        from .narou import render_narou

        return render_narou(document)
    raise ValueError(f"unsupported export format: {format}")


__all__ = ["ExportResult", "ExportWarning", "export_document"]
