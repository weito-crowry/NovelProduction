from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import cast

from novel_core.style_analysis.resolver_candidates import exact_key
from novel_core.style_analysis.term_models import (
    TERM_TYPES,
    TermAliasRecord,
    TermRecord,
)
from novel_core.style_analysis.term_repository import TermRepository


class TermService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.repository = TermRepository(connection)

    def create_manual_term(
        self,
        *,
        reference_work_id: int | None,
        document_id: int | None,
        canonical_label: str,
        term_type: str,
    ) -> TermRecord:
        if (reference_work_id is None) == (document_id is None):
            raise ValueError("TERM_SCOPE_INVALID")
        if term_type not in TERM_TYPES:
            raise ValueError("TERM_TYPE_INVALID")
        if document_id is not None:
            row = self._connection.execute(
                "SELECT reference_episode_id FROM style_documents WHERE id=?",
                (document_id,),
            ).fetchone()
            if row is None:
                raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
            if row[0] is not None:
                raise ValueError("TERM_SCOPE_INVALID")
        label = canonical_label.strip() if isinstance(canonical_label, str) else ""
        if not 1 <= len(label) <= 200:
            raise ValueError("TERM_LABEL_INVALID")
        with self._write_transaction():
            cursor = self._connection.execute(
                "INSERT INTO style_terms "
                "(reference_work_id, document_id, canonical_label, term_type, origin) "
                "VALUES (?, ?, ?, ?, 'manual')",
                (reference_work_id, document_id, label, term_type),
            )
            assert cursor.lastrowid is not None
            return self.repository.get(cursor.lastrowid)

    def create_manual_alias(self, *, term_id: int, alias: str) -> TermAliasRecord:
        normalized = alias.strip() if isinstance(alias, str) else ""
        if not 1 <= len(normalized) <= 200:
            raise ValueError("ALIAS_INVALID")
        self.repository.get(term_id)
        existing = self._connection.execute(
            "SELECT id FROM style_term_aliases "
            "WHERE term_id=? AND alias=? AND origin='manual' ORDER BY id LIMIT 1",
            (term_id, normalized),
        ).fetchone()
        if existing is not None:
            return self.repository.get_alias(int(existing[0]))
        with self._write_transaction():
            return self.repository.insert_alias(
                term_id=term_id,
                alias=normalized,
                origin="manual",
                analysis_run_id=None,
            )

    def exact_matches(
        self, *, document_id: int, surface: str
    ) -> tuple[TermRecord, ...]:
        terms = self.repository.list_for_scope(**self._scope(document_id))
        key = exact_key(surface)
        matches: list[TermRecord] = []
        for term in terms:
            if not self._enabled(term.id):
                continue
            if (
                self._effective_label(term)
                and exact_key(self._effective_label(term)) == key
            ):
                matches.append(term)
                continue
            for alias in self.repository.aliases_for(term.id):
                if (
                    self._alias_is_usable(alias.id, alias.origin)
                    and exact_key(alias.alias) == key
                ):
                    matches.append(term)
                    break
        return tuple(
            sorted({term.id: term for term in matches}.values(), key=lambda x: x.id)
        )

    def candidate_rows(
        self, *, document_id: int, term_type: str, same_scene_ids: set[int]
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for term in self.repository.list_for_scope(**self._scope(document_id)):
            if not self._enabled(term.id):
                continue
            from novel_core.style_analysis.semantic_metric_support import (
                resolve_term_type,
            )

            effective_type = resolve_term_type(self._connection, term.id).value
            if not isinstance(effective_type, str):
                continue
            if term_type != "other" and effective_type != term_type:
                continue
            aliases = [
                alias.alias
                for alias in self.repository.aliases_for(term.id)
                if self._alias_is_usable(alias.id, alias.origin)
            ]
            rows.append(
                {
                    "term_id": term.id,
                    "term_type": effective_type,
                    "canonical_label": self._effective_label(term),
                    "aliases": aliases,
                    "same_scene": term.id in same_scene_ids,
                }
            )
        return rows

    def validate_candidate(self, payload: Mapping[str, object]) -> None:
        if payload.get("term_type_candidate") not in TERM_TYPES:
            raise ValueError("TERM_TYPE_INVALID")
        if not isinstance(payload.get("surface"), str) or not payload["surface"]:
            raise ValueError("TERM_FIELD_INVALID")

    def insert_inferred_alias_if_missing(
        self, *, term_id: int, alias: str, analysis_run_id: int
    ) -> None:
        normalized_alias = alias.strip() if isinstance(alias, str) else ""
        if not normalized_alias:
            return
        term = self.repository.get(term_id)
        values = [self._effective_label(term).strip()] + [
            item.alias for item in self.repository.aliases_for(term_id)
        ]
        if exact_key(normalized_alias) in {
            exact_key(value.strip()) for value in values
        }:
            return
        self.repository.insert_alias(
            term_id=term_id,
            alias=normalized_alias,
            origin="inferred",
            analysis_run_id=analysis_run_id,
        )

    def _scope(self, document_id: int) -> dict[str, int]:
        row = self._connection.execute(
            "SELECT reference_episode_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        if row[0] is None:
            return {"document_id": document_id}
        work_row = self._connection.execute(
            "SELECT reference_work_id FROM style_reference_episodes WHERE id = ?",
            (row[0],),
        ).fetchone()
        if work_row is None:
            raise ValueError("REFERENCE_EPISODE_NOT_FOUND")
        return {"reference_work_id": cast(int, work_row[0])}

    def _enabled(self, term_id: int) -> bool:
        row = self._latest_override(term_id, "term.enabled")
        if row is None or row[0] != "set":
            return True
        try:
            return json.loads(cast(str, row[1])) is not False
        except (TypeError, json.JSONDecodeError):
            return False

    def _effective_label(self, term: TermRecord) -> str:
        row = self._latest_override(term.id, "term.canonical_label")
        if row is None or row[0] != "set":
            return term.canonical_label
        try:
            value = json.loads(cast(str, row[1]))
        except json.JSONDecodeError:
            return term.canonical_label
        return value if isinstance(value, str) and value else term.canonical_label

    def _latest_override(
        self, subject_id: int, field_path: str
    ) -> tuple[object, object] | None:
        from novel_core.style_analysis.semantic_metric_support import latest_override

        row = latest_override(self._connection, "term", subject_id, field_path)
        return None if row is None else (row[1], row[2])

    def _alias_is_usable(self, alias_id: int, origin: str) -> bool:
        if origin == "manual":
            return True
        row = self._connection.execute(
            "SELECT review_status FROM style_inference_reviews "
            "WHERE subject_type = 'term_alias' AND subject_id = ? "
            "AND field_path = 'term_alias.acceptance' "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (alias_id,),
        ).fetchone()
        return row is not None and row[0] == "confirmed"

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        savepoint = "style_term_write"
        owns_transaction = not self._connection.in_transaction
        if owns_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        else:
            self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield
            if owns_transaction:
                self._connection.commit()
            else:
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            else:
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
