from __future__ import annotations


class NovelMcpError(RuntimeError):
    """Base error for MCP lifecycle failures."""


class DocumentSchemaError(ValueError, NovelMcpError):
    """Raised when a Canonical Document violates Schema v1."""

    code = "DOCUMENT_SCHEMA_ERROR"

    def __init__(self, message: str = "invalid Canonical Document") -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class DocumentStorageError(NovelMcpError):
    """Raised when persisted Canonical Document JSON is structurally invalid."""

    code = "DOCUMENT_STORAGE_ERROR"

    def __init__(self, message: str = "stored Canonical Document is invalid") -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class ProjectDraftNotFoundError(NovelMcpError):
    """Raised when a requested project draft does not exist."""

    code = "PROJECT_DRAFT_NOT_FOUND"

    def __init__(self, message: str = "project draft not found") -> None:
        super().__init__(f"{self.code}: {message}")


class ProjectDraftTextProjectionError(NovelMcpError):
    """Raised when a project draft cannot be projected into style text."""

    code = "PROJECT_DRAFT_TEXT_PROJECTION_FAILED"

    def __init__(self, message: str = "project draft text projection failed") -> None:
        super().__init__(f"{self.code}: {message}")


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


class AnalyzerProviderUnavailableError(ValidationError):
    """Raised before a model-backed analysis job is persisted."""

    code = "ANALYZER_PROVIDER_UNAVAILABLE"

    def __init__(self, message: str = "style model provider is unavailable") -> None:
        super().__init__(message)
        self.code = type(self).code
        self.args = (f"{self.code}: {message}",)


class AnalysisCancelledError(NovelMcpError):
    """Raised at an analysis safe point after a job cancellation request."""

    code = "ANALYSIS_CANCELLED"

    def __init__(self, message: str = "style analysis cancelled") -> None:
        super().__init__(f"{self.code}: {message}")


class AnalysisExecutionConflictError(NovelMcpError):
    code = "ANALYSIS_EXECUTION_CONFLICT"

    def __init__(
        self, message: str = "analysis execution conflicts with an active execution"
    ) -> None:
        super().__init__(f"{self.code}: {message}")


class ExternalAnalysisSessionNotFoundError(NovelMcpError):
    code = "NOT_FOUND"


class ExternalAnalysisTaskNotFoundError(NovelMcpError):
    code = "NOT_FOUND"


class ExternalSessionTerminalError(NovelMcpError):
    code = "EXTERNAL_SESSION_TERMINAL"


class ExternalTaskAlreadyFinalizedError(NovelMcpError):
    code = "EXTERNAL_TASK_ALREADY_FINALIZED"


class ExternalTaskNotCurrentError(NovelMcpError):
    code = "EXTERNAL_TASK_NOT_CURRENT"


class ExternalExecutorMismatchError(NovelMcpError):
    code = "EXTERNAL_EXECUTOR_MISMATCH"


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
