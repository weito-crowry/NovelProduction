from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChapterRecord:
    id: int
    work_id: int
    position: int
    title: str
    summary: str
    purpose: str
    canon_status: str
    production_status: str
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class EpisodeRecord:
    id: int
    work_id: int
    chapter_id: int
    position: int
    title: str
    summary: str
    purpose: str
    foreshadowing_notes_json: str
    canon_status: str
    production_status: str
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SceneRecord:
    id: int
    work_id: int
    episode_id: int
    position: int
    title: str
    summary: str
    purpose: str
    canon_status: str
    production_status: str
    version: int
    created_at: str
    updated_at: str


_CHAPTER_COLUMNS = (
    "id, work_id, position, title, summary, purpose, canon_status, "
    "production_status, version, created_at, updated_at"
)
_EPISODE_COLUMNS = (
    "id, work_id, chapter_id, position, title, summary, purpose, "
    "foreshadowing_notes_json, canon_status, production_status, version, "
    "created_at, updated_at"
)
_SCENE_COLUMNS = (
    "id, work_id, episode_id, position, title, summary, purpose, canon_status, "
    "production_status, version, created_at, updated_at"
)


class NarrativeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_write(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def create_chapter(self, *, work_id: int, fields: Mapping[str, object]) -> int:
        return self._create(
            "chapters", "work_id", work_id, fields, "position", "work_id = ?"
        )

    def create_episode(
        self, *, work_id: int, chapter_id: int, fields: Mapping[str, object]
    ) -> int:
        return self._create(
            "episodes",
            "chapter_id",
            chapter_id,
            fields,
            "position",
            "chapter_id = ?",
            work_id=work_id,
        )

    def create_scene(
        self, *, work_id: int, episode_id: int, fields: Mapping[str, object]
    ) -> int:
        return self._create(
            "scenes",
            "episode_id",
            episode_id,
            fields,
            "position",
            "episode_id = ?",
            work_id=work_id,
        )

    def get_chapter(self, *, work_id: int, chapter_id: int) -> ChapterRecord | None:
        row = self._connection.execute(
            f"SELECT {_CHAPTER_COLUMNS} FROM chapters WHERE work_id = ? AND id = ?",
            (work_id, chapter_id),
        ).fetchone()
        return None if row is None else ChapterRecord(*row)

    def get_episode(self, *, work_id: int, episode_id: int) -> EpisodeRecord | None:
        row = self._connection.execute(
            f"SELECT {_EPISODE_COLUMNS} FROM episodes WHERE work_id = ? AND id = ?",
            (work_id, episode_id),
        ).fetchone()
        return None if row is None else EpisodeRecord(*row)

    def get_scene(self, *, work_id: int, scene_id: int) -> SceneRecord | None:
        row = self._connection.execute(
            f"SELECT {_SCENE_COLUMNS} FROM scenes WHERE work_id = ? AND id = ?",
            (work_id, scene_id),
        ).fetchone()
        return None if row is None else SceneRecord(*row)

    def list_chapters(self, *, work_id: int) -> tuple[ChapterRecord, ...]:
        rows = self._connection.execute(
            f"SELECT {_CHAPTER_COLUMNS} FROM chapters "
            "WHERE work_id = ? ORDER BY position, id",
            (work_id,),
        ).fetchall()
        return tuple(ChapterRecord(*row) for row in rows)

    def list_episodes(
        self, *, work_id: int, chapter_id: int
    ) -> tuple[EpisodeRecord, ...]:
        rows = self._connection.execute(
            f"SELECT {_EPISODE_COLUMNS} FROM episodes "
            "WHERE work_id = ? AND chapter_id = ? ORDER BY position, id",
            (work_id, chapter_id),
        ).fetchall()
        return tuple(EpisodeRecord(*row) for row in rows)

    def list_scenes(self, *, work_id: int, episode_id: int) -> tuple[SceneRecord, ...]:
        rows = self._connection.execute(
            f"SELECT {_SCENE_COLUMNS} FROM scenes "
            "WHERE work_id = ? AND episode_id = ? ORDER BY position, id",
            (work_id, episode_id),
        ).fetchall()
        return tuple(SceneRecord(*row) for row in rows)

    def reorder_positions(
        self,
        *,
        table: str,
        parent_column: str,
        work_id: int,
        parent_id: int,
        final_positions: Mapping[int, int],
        affected_ids: tuple[int, ...],
    ) -> None:
        rows = self._connection.execute(
            f"SELECT id, position FROM {table} WHERE work_id = ? "
            f"AND {parent_column} = ? "
            "ORDER BY position, id",
            (work_id, parent_id),
        ).fetchall()
        temporary_base = max(int(row[1]) for row in rows)
        for index, row in enumerate(rows, start=1):
            self._connection.execute(
                f"UPDATE {table} SET position = ? "
                f"WHERE work_id = ? AND {parent_column} = ? AND id = ?",
                (temporary_base + index, work_id, parent_id, int(row[0])),
            )
        for entity_id in affected_ids:
            self._connection.execute(
                f"UPDATE {table} SET position = ?, version = version + 1, "
                "updated_at = CURRENT_TIMESTAMP "
                f"WHERE work_id = ? AND {parent_column} = ? AND id = ?",
                (
                    final_positions[entity_id],
                    work_id,
                    parent_id,
                    entity_id,
                ),
            )

    def update(
        self,
        *,
        table: str,
        entity_id: int,
        work_id: int,
        expected_version: int,
        fields: Mapping[str, object],
    ) -> bool:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        cursor = self._connection.execute(
            f"UPDATE {table} SET {assignments}, updated_at = CURRENT_TIMESTAMP, "
            "version = version + 1 WHERE work_id = ? AND id = ? AND version = ?",
            (*fields.values(), work_id, entity_id, expected_version),
        )
        return cursor.rowcount == 1

    def _create(
        self,
        table: str,
        parent_column: str,
        parent_id: int,
        fields: Mapping[str, object],
        position_column: str,
        where_clause: str,
        *,
        work_id: int | None = None,
    ) -> int:
        parent_values: tuple[object, ...]
        if work_id is None:
            parent_values = (parent_id,)
        else:
            parent_values = (parent_id,)
        position = self._connection.execute(
            f"SELECT COALESCE(MAX({position_column}), 0) + 1 FROM {table} "
            f"WHERE {where_clause}",
            parent_values,
        ).fetchone()[0]
        values = {position_column: position, **fields}
        if work_id is None:
            columns = ("work_id", *values.keys())
            parameters = (parent_id, *values.values())
        elif table == "episodes":
            columns = ("work_id", "chapter_id", *values.keys())
            parameters = (work_id, parent_id, *values.values())
        else:
            columns = ("work_id", "episode_id", *values.keys())
            parameters = (work_id, parent_id, *values.values())
        placeholders = ", ".join("?" for _ in parameters)
        cursor = self._connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            parameters,
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError(f"{table} insert did not return an id")
        return cursor.lastrowid
