from __future__ import annotations

import sqlite3

from novel_mcp.models.outline import ProtectedInformationGuard


class ContextGuardService:
    """Expose the safe, relevant guards for a narrative-boundary read."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def check_context_guards(
        self, episode_id: int
    ) -> tuple[ProtectedInformationGuard, ...]:
        from novel_mcp.services.context_service import ContextService

        return (
            ContextService(self._connection)
            .build_episode_context(episode_id)
            .protected_information_guards
        )


def check_context_guards(
    connection: sqlite3.Connection, episode_id: int
) -> tuple[ProtectedInformationGuard, ...]:
    return ContextGuardService(connection).check_context_guards(episode_id)
