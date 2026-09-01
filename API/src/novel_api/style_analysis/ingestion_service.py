from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import cast

from novel_core.config import DatabaseConfig
from novel_core.database import (
    default_migration_dir,
    open_database,
    open_database_readonly,
)
from novel_core.style_analysis.source_models import (
    SourceEpisodeInput,
    SourceWorkInput,
)
from novel_core.style_analysis.source_repository import StyleSourceRepository

from novel_api.service_container import ProjectTarget
from novel_api.style_analysis.adapters import get_source_adapter
from novel_api.style_analysis.adapters.base import (
    SourceRequest,
    SourceTooLargeError,
    SourceType,
)

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SourceImportOutcome:
    reused_existing: bool
    reference_work_id: int
    source_id: int


def import_source(
    target: ProjectTarget,
    *,
    source_type: str,
    filename: str,
    payload: bytes,
    media_type: str,
) -> SourceImportOutcome:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise SourceTooLargeError("source upload is too large")

    adapter = get_source_adapter(source_type)
    request = SourceRequest(
        source_type=cast(SourceType, source_type),
        filename=filename,
        payload=payload,
    )
    identity = adapter.identify(request)
    with _open_connection(target, readonly=True) as connection:
        existing = StyleSourceRepository(connection).find_by_identity(
            source_type, identity.external_work_id
        )
    if existing is not None:
        return SourceImportOutcome(
            reused_existing=True,
            reference_work_id=existing.id,
            source_id=existing.source_id,
        )

    imported = adapter.import_work(request)
    work = SourceWorkInput(
        title=imported.title,
        author_name=imported.author_name,
        metadata=imported.metadata,
        episodes=tuple(
            SourceEpisodeInput(
                external_episode_id=episode.external_episode_id,
                title=episode.title,
                order_index=episode.order_index,
                raw_text=episode.raw_text,
                metadata=episode.metadata,
            )
            for episode in imported.episodes
        ),
    )

    with _open_connection(target, readonly=False) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            repository = StyleSourceRepository(connection)
            existing = repository.find_by_identity(
                source_type, identity.external_work_id
            )
            if existing is not None:
                connection.rollback()
                return SourceImportOutcome(
                    reused_existing=True,
                    reference_work_id=existing.id,
                    source_id=existing.source_id,
                )
            inserted = repository.insert_import(
                source_type=source_type,
                external_work_id=identity.external_work_id,
                original_filename=filename,
                adapter_id=adapter.adapter_id,
                adapter_version=adapter.adapter_version,
                payload=payload,
                media_type=media_type,
                source_metadata={},
                work=work,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return SourceImportOutcome(
        reused_existing=False,
        reference_work_id=inserted.work.id,
        source_id=inserted.source.id,
    )


@contextmanager
def _open_connection(
    target: ProjectTarget, *, readonly: bool
) -> Iterator[sqlite3.Connection]:
    config = DatabaseConfig(
        db_path=target.descriptor.story_db,
        migration_dir=default_migration_dir(),
    )
    connection = open_database_readonly(config) if readonly else open_database(config)
    try:
        yield connection
    finally:
        connection.close()
