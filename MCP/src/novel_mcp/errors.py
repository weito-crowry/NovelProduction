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


class WorldFactNotFoundError(NovelMcpError):
    """Raised when a requested world fact does not exist."""


class CharacterNotFoundError(NovelMcpError):
    """Raised when a requested character does not exist in the work."""


class RelationshipNotFoundError(NovelMcpError):
    """Raised when a requested relationship does not exist in the work."""


class ValidationError(ValueError, NovelMcpError):
    """Raised for invalid input with a stable machine-readable code."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.code = "VALIDATION_ERROR"
        self.field = field
        self.message = message
        super().__init__(f"{self.code}: {message}")
