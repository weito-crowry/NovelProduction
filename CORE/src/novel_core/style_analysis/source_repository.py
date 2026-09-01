from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from typing import cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.fingerprints import JsonObject
from novel_core.style_analysis.source_models import (
    ReferenceEpisodeRecord,
    ReferenceWorkRecord,
    SourceImportResult,
    SourceType,
    SourceWorkInput,
    StyleSourceRecord,
    StyleSourceSnapshotRecord,
)
from novel_core.style_analysis.text_service import StyleTextService

_SOURCE_COLUMNS = (
    "id, source_type, external_work_id, original_filename, adapter_id, "
    "adapter_version, created_at"
)
_WORK_COLUMNS = (
    "rw.id, rw.source_id, s.source_type, s.external_work_id, rw.title, "
    "rw.author_name, rw.metadata_json, rw.created_at, rw.updated_at, "
    "COUNT(re.id)"
)
_EPISODE_COLUMNS = (
    "re.id, re.reference_work_id, re.external_episode_id, re.title, "
    "re.order_index, re.latest_snapshot_id, re.metadata_json, re.created_at, "
    "re.updated_at, sd.id, sd.current_text_revision_id, "
    "sd.current_structure_revision_id, sr.source_kind, tr.canonical_text, "
    "tr.metadata_json"
)
_EPISODE_COLUMNS_WITH_SOURCES = f"{_EPISODE_COLUMNS}, rw.source_id, ss.source_id"


class StyleSourceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._text_service = StyleTextService(connection)

    def find_by_identity(
        self, source_type: str, external_work_id: str
    ) -> ReferenceWorkRecord | None:
        row = self._connection.execute(
            f"SELECT {_WORK_COLUMNS} FROM style_reference_works AS rw "
            "JOIN style_sources AS s ON s.id = rw.source_id "
            "LEFT JOIN style_reference_episodes AS re "
            "ON re.reference_work_id = rw.id "
            "WHERE s.source_type = ? AND s.external_work_id = ? "
            "GROUP BY rw.id",
            (source_type, external_work_id),
        ).fetchone()
        return None if row is None else _work_from_row(row)

    def insert_import(
        self,
        *,
        source_type: str,
        external_work_id: str,
        original_filename: str,
        adapter_id: str,
        adapter_version: int,
        payload: bytes,
        media_type: str,
        source_metadata: JsonObject,
        work: SourceWorkInput,
    ) -> SourceImportResult:
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        if payload_sha256 != external_work_id:
            raise ValidationError("SOURCE_IDENTITY_MISMATCH")
        source_cursor = self._connection.execute(
            "INSERT INTO style_sources "
            "(source_type, external_work_id, original_filename, adapter_id, "
            "adapter_version) VALUES (?, ?, ?, ?, ?)",
            (
                source_type,
                external_work_id,
                original_filename,
                adapter_id,
                adapter_version,
            ),
        )
        source_id = _lastrowid(source_cursor, "source")
        source = self._get_source(source_id)
        if source is None:
            raise RuntimeError("source insert could not be read")
        snapshot_cursor = self._connection.execute(
            "INSERT INTO style_source_snapshots "
            "(source_id, filename, media_type, payload_sha256, raw_payload, "
            "metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                source_id,
                original_filename,
                media_type,
                payload_sha256,
                payload,
                _json(source_metadata),
            ),
        )
        snapshot_id = _lastrowid(snapshot_cursor, "source snapshot")
        snapshot = self._get_snapshot(snapshot_id)
        if snapshot is None:
            raise RuntimeError("source snapshot insert could not be read")
        work_cursor = self._connection.execute(
            "INSERT INTO style_reference_works "
            "(source_id, title, author_name, metadata_json) VALUES (?, ?, ?, ?)",
            (source_id, work.title, work.author_name, _json(work.metadata)),
        )
        work_id = _lastrowid(work_cursor, "reference work")
        for episode in sorted(work.episodes, key=lambda item: item.order_index):
            episode_cursor = self._connection.execute(
                "INSERT INTO style_reference_episodes "
                "(reference_work_id, external_episode_id, title, order_index, "
                "latest_snapshot_id, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    work_id,
                    episode.external_episode_id,
                    episode.title,
                    episode.order_index,
                    snapshot_id,
                    _json(episode.metadata),
                ),
            )
            episode_id = _lastrowid(episode_cursor, "reference episode")
            document_cursor = self._connection.execute(
                "INSERT INTO style_documents (kind, reference_episode_id) "
                "VALUES ('reference_episode', ?)",
                (episode_id,),
            )
            document_id = _lastrowid(document_cursor, "style document")
            self._text_service.insert_normalized_reference_revision(
                document_id=document_id,
                source_snapshot_id=snapshot_id,
                raw_text=episode.raw_text,
                structure_hints_raw=episode.metadata.get("scene_break_offsets_raw", []),
            )
        result_work = self.get_reference_work(work_id)
        if result_work is None:
            raise RuntimeError("reference work insert could not be read")
        return SourceImportResult(source, snapshot, result_work)

    def list_reference_works(self) -> tuple[ReferenceWorkRecord, ...]:
        rows = self._connection.execute(
            f"SELECT {_WORK_COLUMNS} FROM style_reference_works AS rw "
            "JOIN style_sources AS s ON s.id = rw.source_id "
            "LEFT JOIN style_reference_episodes AS re "
            "ON re.reference_work_id = rw.id GROUP BY rw.id "
            "ORDER BY rw.id"
        ).fetchall()
        return tuple(_work_from_row(row) for row in rows)

    def get_reference_work(self, work_id: int) -> ReferenceWorkRecord | None:
        row = self._connection.execute(
            f"SELECT {_WORK_COLUMNS} FROM style_reference_works AS rw "
            "JOIN style_sources AS s ON s.id = rw.source_id "
            "LEFT JOIN style_reference_episodes AS re "
            "ON re.reference_work_id = rw.id WHERE rw.id = ? GROUP BY rw.id",
            (work_id,),
        ).fetchone()
        return None if row is None else _work_from_row(row)

    def list_reference_episodes(
        self, work_id: int
    ) -> tuple[ReferenceEpisodeRecord, ...]:
        rows = self._connection.execute(
            f"SELECT {_EPISODE_COLUMNS_WITH_SOURCES} "
            "FROM style_reference_episodes AS re "
            "JOIN style_reference_works AS rw ON rw.id = re.reference_work_id "
            "JOIN style_sources AS s ON s.id = rw.source_id "
            "JOIN style_source_snapshots AS ss ON ss.id = re.latest_snapshot_id "
            "LEFT JOIN style_documents AS sd ON sd.reference_episode_id = re.id "
            "LEFT JOIN style_text_revisions AS tr "
            "ON tr.id = sd.current_text_revision_id "
            "LEFT JOIN style_structure_revisions AS sr "
            "ON sr.id = sd.current_structure_revision_id "
            "WHERE re.reference_work_id = ? ORDER BY re.order_index",
            (work_id,),
        ).fetchall()
        return tuple(self._validated_episode_from_row(row) for row in rows)

    def get_reference_episode(self, episode_id: int) -> ReferenceEpisodeRecord | None:
        row = self._connection.execute(
            f"SELECT {_EPISODE_COLUMNS_WITH_SOURCES} "
            "FROM style_reference_episodes AS re "
            "JOIN style_reference_works AS rw ON rw.id = re.reference_work_id "
            "JOIN style_sources AS s ON s.id = rw.source_id "
            "JOIN style_source_snapshots AS ss ON ss.id = re.latest_snapshot_id "
            "LEFT JOIN style_documents AS sd ON sd.reference_episode_id = re.id "
            "LEFT JOIN style_text_revisions AS tr "
            "ON tr.id = sd.current_text_revision_id "
            "LEFT JOIN style_structure_revisions AS sr "
            "ON sr.id = sd.current_structure_revision_id "
            "WHERE re.id = ?",
            (episode_id,),
        ).fetchone()
        if row is None:
            return None
        return self._validated_episode_from_row(row)

    def purge_reference_work(self, work_id: int) -> bool:
        row = self._connection.execute(
            "SELECT source_id FROM style_reference_works WHERE id = ?", (work_id,)
        ).fetchone()
        if row is None:
            return False
        cursor = self._connection.execute(
            "DELETE FROM style_sources WHERE id = ?", (row[0],)
        )
        return cursor.rowcount == 1

    def _get_source(self, source_id: int) -> StyleSourceRecord | None:
        row = self._connection.execute(
            f"SELECT {_SOURCE_COLUMNS} FROM style_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        return None if row is None else _source_from_row(row)

    def _get_snapshot(self, snapshot_id: int) -> StyleSourceSnapshotRecord | None:
        row = self._connection.execute(
            "SELECT id, source_id, filename, media_type, payload_sha256, "
            "raw_payload, metadata_json, created_at FROM style_source_snapshots "
            "WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        return None if row is None else StyleSourceSnapshotRecord(*row)

    def _episode_from_row(self, row: Sequence[object]) -> ReferenceEpisodeRecord:
        return ReferenceEpisodeRecord(
            id=cast(int, row[0]),
            reference_work_id=cast(int, row[1]),
            external_episode_id=cast(str, row[2]),
            title=cast(str, row[3]),
            order_index=cast(int, row[4]),
            latest_snapshot_id=cast(int, row[5]),
            metadata_json=cast(str, row[6]),
            created_at=cast(str, row[7]),
            updated_at=cast(str, row[8]),
            style_document_id=cast(int | None, row[9]),
            current_text_revision_id=cast(int | None, row[10]),
            current_structure_revision_id=cast(int | None, row[11]),
            current_structure_kind=cast(str | None, row[12]),
            current_text=cast(str | None, row[13]),
            document_metadata_json=cast(str | None, row[14]),
        )

    def _validated_episode_from_row(
        self, row: Sequence[object]
    ) -> ReferenceEpisodeRecord:
        if row[-2] != row[-1]:
            raise ValidationError("SOURCE_SNAPSHOT_WORK_MISMATCH")
        return self._episode_from_row(row)


def _lastrowid(cursor: sqlite3.Cursor, label: str) -> int:
    if cursor.lastrowid is None:
        raise sqlite3.IntegrityError(f"{label} insert did not return an id")
    return cursor.lastrowid


def _json(value: JsonObject) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _source_from_row(row: Sequence[object]) -> StyleSourceRecord:
    return StyleSourceRecord(
        id=cast(int, row[0]),
        source_type=cast(SourceType, row[1]),
        external_work_id=cast(str, row[2]),
        original_filename=cast(str, row[3]),
        adapter_id=cast(str, row[4]),
        adapter_version=cast(int, row[5]),
        created_at=cast(str, row[6]),
    )


def _work_from_row(row: Sequence[object]) -> ReferenceWorkRecord:
    return ReferenceWorkRecord(
        id=cast(int, row[0]),
        source_id=cast(int, row[1]),
        source_type=cast(SourceType, row[2]),
        external_work_id=cast(str, row[3]),
        title=cast(str, row[4]),
        author_name=cast(str | None, row[5]),
        metadata_json=cast(str, row[6]),
        created_at=cast(str, row[7]),
        updated_at=cast(str, row[8]),
        episode_count=cast(int, row[9]),
    )
