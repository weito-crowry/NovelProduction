from __future__ import annotations

import sqlite3

from novel_mcp.errors import WorkNotFoundError
from novel_mcp.repositories.character_repository import CharacterRecord
from novel_mcp.repositories.search_repository import SearchDiagnostic, SearchRepository
from novel_mcp.repositories.work_repository import WorkRepository
from novel_mcp.repositories.world_fact_repository import WorldFactRecord

MAX_SEARCH_LIMIT = 100


class SearchService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._work_repository = WorkRepository(connection)
        self._repository = SearchRepository(connection)

    def search_world_facts(self, query: str, limit: int) -> tuple[WorldFactRecord, ...]:
        normalized_query, bounded_limit = self._validate_search(query, limit)
        if not normalized_query or bounded_limit == 0:
            return ()
        return self._repository.search_world_facts(
            work_id=self._work_id(), query=normalized_query, limit=bounded_limit
        )

    def search_characters(self, query: str, limit: int) -> tuple[CharacterRecord, ...]:
        normalized_query, bounded_limit = self._validate_search(query, limit)
        if not normalized_query or bounded_limit == 0:
            return ()
        return self._repository.search_characters(
            work_id=self._work_id(), query=normalized_query, limit=bounded_limit
        )

    def diagnose_world_facts(self, query: str, limit: int) -> SearchDiagnostic:
        normalized_query, bounded_limit = self._validate_search(query, limit)
        if not normalized_query or bounded_limit == 0:
            return SearchDiagnostic(
                (), normalized_query, self._work_id(), bounded_limit, "none"
            )
        return self._repository.diagnose_world_facts(
            work_id=self._work_id(), query=normalized_query, limit=bounded_limit
        )

    def diagnose_characters(self, query: str, limit: int) -> SearchDiagnostic:
        normalized_query, bounded_limit = self._validate_search(query, limit)
        if not normalized_query or bounded_limit == 0:
            return SearchDiagnostic(
                (), normalized_query, self._work_id(), bounded_limit, "none"
            )
        return self._repository.diagnose_characters(
            work_id=self._work_id(), query=normalized_query, limit=bounded_limit
        )

    def _work_id(self) -> int:
        work = self._work_repository.get()
        if work is None:
            raise WorkNotFoundError("WORK_NOT_FOUND")
        return work.id

    def _validate_search(self, query: str, limit: int) -> tuple[str, int]:
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        if not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        return query.strip(), min(max(limit, 0), MAX_SEARCH_LIMIT)
