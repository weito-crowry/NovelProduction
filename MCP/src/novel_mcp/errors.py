from __future__ import annotations


class NovelMcpError(RuntimeError):
    """Base error for MCP lifecycle failures."""


class MigrationError(NovelMcpError):
    """Raised when migrations cannot be applied safely."""
