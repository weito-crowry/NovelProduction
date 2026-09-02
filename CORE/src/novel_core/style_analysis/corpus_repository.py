from __future__ import annotations

import sqlite3
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.corpus_models import (
    CorpusEpisodeMembershipRecord,
    CorpusRecord,
    CorpusWorkMembershipRecord,
    EpisodeMembershipMode,
)


class CorpusRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, name: str, description: str = "") -> CorpusRecord:
        if not isinstance(name, str) or not name:
            raise ValidationError("CORPUS_NAME_REQUIRED")
        cursor = self._connection.execute(
            "INSERT INTO style_corpora (name, description) VALUES (?, ?)",
            (name, description),
        )
        assert cursor.lastrowid is not None
        result = self.get(cursor.lastrowid)
        assert result is not None
        return result

    def get(self, corpus_id: int) -> CorpusRecord | None:
        row = self._connection.execute(
            "SELECT id, name, description, created_at, updated_at "
            "FROM style_corpora WHERE id = ?",
            (corpus_id,),
        ).fetchone()
        return None if row is None else CorpusRecord(*row)

    def list(self) -> tuple[CorpusRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, name, description, created_at, updated_at "
            "FROM style_corpora ORDER BY id"
        ).fetchall()
        return tuple(CorpusRecord(*row) for row in rows)

    def update(
        self, corpus_id: int, *, name: str | None = None, description: str | None = None
    ) -> CorpusRecord:
        current = self.get(corpus_id)
        if current is None:
            raise ValidationError("CORPUS_NOT_FOUND")
        if name is not None and (not isinstance(name, str) or not name):
            raise ValidationError("CORPUS_NAME_REQUIRED")
        self._connection.execute(
            "UPDATE style_corpora SET name = COALESCE(?, name), "
            "description = COALESCE(?, description), updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (name, description, corpus_id),
        )
        result = self.get(corpus_id)
        assert result is not None
        return result

    def delete(self, corpus_id: int) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM style_corpora WHERE id = ?", (corpus_id,)
        )
        return cursor.rowcount == 1

    def add_work(
        self, corpus_id: int, reference_work_id: int, *, include_all_episodes: bool
    ) -> CorpusWorkMembershipRecord:
        self._require_corpus(corpus_id)
        if (
            self._connection.execute(
                "SELECT 1 FROM style_reference_works WHERE id = ?", (reference_work_id,)
            ).fetchone()
            is None
        ):
            raise ValidationError("REFERENCE_WORK_NOT_FOUND")
        cursor = self._connection.execute(
            "INSERT INTO style_corpus_work_memberships "
            "(corpus_id, reference_work_id, include_all_episodes) VALUES (?, ?, ?)",
            (corpus_id, reference_work_id, int(include_all_episodes)),
        )
        assert cursor.lastrowid is not None
        return self.get_work_membership(cursor.lastrowid)

    def get_work_membership(self, membership_id: int) -> CorpusWorkMembershipRecord:
        row = self._connection.execute(
            "SELECT id, corpus_id, reference_work_id, include_all_episodes, created_at "
            "FROM style_corpus_work_memberships WHERE id = ?",
            (membership_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("CORPUS_WORK_MEMBERSHIP_NOT_FOUND")
        return CorpusWorkMembershipRecord(
            id=cast(int, row[0]),
            corpus_id=cast(int, row[1]),
            reference_work_id=cast(int, row[2]),
            include_all_episodes=bool(row[3]),
            created_at=cast(str, row[4]),
        )

    def list_work_memberships(
        self, corpus_id: int
    ) -> tuple[CorpusWorkMembershipRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, corpus_id, reference_work_id, include_all_episodes, created_at "
            "FROM style_corpus_work_memberships WHERE corpus_id = ? ORDER BY id",
            (corpus_id,),
        ).fetchall()
        return tuple(
            CorpusWorkMembershipRecord(
                id=cast(int, row[0]),
                corpus_id=cast(int, row[1]),
                reference_work_id=cast(int, row[2]),
                include_all_episodes=bool(row[3]),
                created_at=cast(str, row[4]),
            )
            for row in rows
        )

    def remove_work(self, corpus_id: int, reference_work_id: int) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM style_corpus_work_memberships "
            "WHERE corpus_id = ? AND reference_work_id = ?",
            (corpus_id, reference_work_id),
        )
        return cursor.rowcount == 1

    def set_episode(
        self, corpus_id: int, reference_episode_id: int, mode: EpisodeMembershipMode
    ) -> CorpusEpisodeMembershipRecord:
        if mode not in {"include", "exclude"}:
            raise ValidationError("CORPUS_EPISODE_MODE_INVALID")
        row = self._connection.execute(
            "SELECT wm.id, re.reference_work_id "
            "FROM style_corpus_work_memberships wm "
            "JOIN style_reference_episodes re "
            "ON re.reference_work_id = wm.reference_work_id "
            "WHERE wm.corpus_id = ? AND re.id = ?",
            (corpus_id, reference_episode_id),
        ).fetchone()
        if row is None:
            raise ValidationError("CORPUS_EPISODE_MEMBERSHIP_SCOPE_INVALID")
        work_membership_id = int(row[0])
        existing = self._connection.execute(
            "SELECT id FROM style_corpus_episode_memberships "
            "WHERE work_membership_id = ? AND reference_episode_id = ?",
            (work_membership_id, reference_episode_id),
        ).fetchone()
        if existing is None:
            cursor = self._connection.execute(
                "INSERT INTO style_corpus_episode_memberships "
                "(work_membership_id, reference_episode_id, mode) VALUES (?, ?, ?)",
                (work_membership_id, reference_episode_id, mode),
            )
            assert cursor.lastrowid is not None
            membership_id = cursor.lastrowid
        else:
            membership_id = int(existing[0])
            self._connection.execute(
                "UPDATE style_corpus_episode_memberships SET mode = ? WHERE id = ?",
                (mode, membership_id),
            )
        return self.get_episode_membership(membership_id)

    def get_episode_membership(
        self, membership_id: int
    ) -> CorpusEpisodeMembershipRecord:
        row = self._connection.execute(
            "SELECT id, work_membership_id, reference_episode_id, mode, created_at "
            "FROM style_corpus_episode_memberships WHERE id = ?",
            (membership_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("CORPUS_EPISODE_MEMBERSHIP_NOT_FOUND")
        return CorpusEpisodeMembershipRecord(*row)

    def remove_episode(self, corpus_id: int, reference_episode_id: int) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM style_corpus_episode_memberships "
            "WHERE reference_episode_id = ? AND work_membership_id IN "
            "(SELECT id FROM style_corpus_work_memberships WHERE corpus_id = ?)",
            (reference_episode_id, corpus_id),
        )
        return cursor.rowcount == 1

    def list_effective_episode_ids(self, corpus_id: int) -> tuple[int, ...]:
        self._require_corpus(corpus_id)
        result: list[int] = []
        for membership in self.list_work_memberships(corpus_id):
            rows = self._connection.execute(
                "SELECT re.id, cem.mode "
                "FROM style_reference_episodes re "
                "LEFT JOIN style_corpus_episode_memberships cem "
                "ON cem.reference_episode_id = re.id "
                "AND cem.work_membership_id = ? "
                "WHERE re.reference_work_id = ? ORDER BY re.order_index, re.id",
                (membership.id, membership.reference_work_id),
            ).fetchall()
            for episode_id, mode in rows:
                included = membership.include_all_episodes
                if mode == "include":
                    included = True
                elif mode == "exclude":
                    included = False
                if included:
                    result.append(int(episode_id))
        return tuple(result)

    def _require_corpus(self, corpus_id: int) -> CorpusRecord:
        corpus = self.get(corpus_id)
        if corpus is None:
            raise ValidationError("CORPUS_NOT_FOUND")
        return corpus
