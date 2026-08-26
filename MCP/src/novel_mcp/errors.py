from __future__ import annotations


class NovelMcpError(RuntimeError):
    """Base error for MCP lifecycle failures."""


class MigrationError(NovelMcpError):
    """Raised when migrations cannot be applied safely."""


class VersionConflictError(NovelMcpError):
    """Raised when optimistic concurrency checks fail."""


class WorkExistsError(NovelMcpError):
    """Raised when explicit initialization is attempted twice."""


class WorkNotFoundError(NovelMcpError):
    """Raised when a requested work record does not exist."""
