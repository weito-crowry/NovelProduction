from __future__ import annotations


class NovelMcpError(RuntimeError):
    """Base error for MCP lifecycle failures."""


class MigrationError(NovelMcpError):
    """Raised when migrations cannot be applied safely."""


class DatabaseIntegrityError(NovelMcpError):
    """Raised when SQLite integrity verification fails."""


class VersionConflictError(NovelMcpError):
    """Raised when optimistic concurrency checks fail."""


class WorkExistsError(NovelMcpError):
    """Raised when explicit initialization is attempted twice."""


class WorkNotFoundError(NovelMcpError):
    """Raised when a requested work record does not exist."""


class WorldFactNotFoundError(NovelMcpError):
    """Raised when a requested world fact does not exist."""


class TimelineEventNotFoundError(NovelMcpError):
    """Raised when a requested timeline event does not exist in the work."""


class CharacterNotFoundError(NovelMcpError):
    """Raised when a requested character does not exist in the work."""


class RelationshipNotFoundError(NovelMcpError):
    """Raised when a requested relationship does not exist in the work."""


class NarrativeNotFoundError(NovelMcpError):
    """Raised when a narrative entity does not exist in the work."""

    code = "NOT_FOUND"

    def __init__(self, message: str = "NOT_FOUND") -> None:
        super().__init__(message)


class OrderConflictError(NovelMcpError):
    """Raised when a narrative reorder target is invalid."""

    code = "ORDER_CONFLICT"

    def __init__(self, message: str = "invalid narrative position") -> None:
        super().__init__(f"{self.code}: {message}")


class WorkScopeError(NovelMcpError):
    """Raised when an entity belongs to another configured work."""

    code = "WORK_SCOPE_ERROR"

    def __init__(self, message: str = "entity belongs to another work") -> None:
        super().__init__(f"{self.code}: {message}")


class DeprecatedCanonForbiddenError(NovelMcpError):
    """Raised when a narrative-boundary read targets deprecated canon."""

    code = "DEPRECATED_CANON_FORBIDDEN"

    def __init__(
        self, message: str = "deprecated canon cannot be used as active context"
    ) -> None:
        super().__init__(f"{self.code}: {message}")


class ValidationError(ValueError, NovelMcpError):
    """Raised for invalid input with a stable machine-readable code."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.code = "VALIDATION_ERROR"
        self.field = field
        self.message = message
        super().__init__(f"{self.code}: {message}")


class RelationshipIntegrityError(ValidationError):
    """Raised when relationship temporal ranges are ambiguous."""

    code = "RELATION_INTEGRITY_ERROR"

    def __init__(self, message: str = "relationship interval overlaps") -> None:
        super().__init__(message)
        self.code = type(self).code
        self.args = (f"{self.code}: {message}",)


class CanonReasonRequired(NovelMcpError):
    """Raised when a protected canon mutation has no reason."""

    code = "CANON_REASON_REQUIRED"

    def __init__(self, message: str = "reason is required") -> None:
        super().__init__(f"{self.code}: {message}")


class CanonPolicyError(NovelMcpError):
    """Raised when a canon mutation violates the canon policy."""

    code = "CANON_POLICY_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


class CanonDecisionNotFoundError(NovelMcpError):
    """Raised when a canon decision is absent."""

    code = "NOT_FOUND"

    def __init__(self, message: str = "NOT_FOUND") -> None:
        super().__init__(message)


class CanonEntityNotFoundError(NovelMcpError):
    """Raised when a requested canon entity is absent from the work."""

    code = "NOT_FOUND"

    def __init__(self, message: str = "NOT_FOUND") -> None:
        super().__init__(message)
