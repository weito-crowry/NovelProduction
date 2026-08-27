from __future__ import annotations

import json
from pathlib import Path

from novel_core.config import DatabaseConfig
from novel_core.database import default_migration_dir, open_database
from novel_core.errors import WorkExistsError
from novel_core.repositories.work_repository import WorkRecord, WorkRepository
from novel_core.services.work_service import PRODUCTION_STATUSES

DEFAULT_WORK_SLUG = "main"


def initialize_work(
    db_path: Path,
    title: str | None = None,
    *,
    working_title: str | None = None,
    genre: str = "",
    premise: str = "",
    themes_json: str = "{}",
    description: str = "",
    production_status: str = "planned",
    migration_dir: Path | None = None,
) -> WorkRecord:
    normalized_title = (
        working_title if working_title is not None else title or ""
    ).strip()
    if not normalized_title:
        raise ValueError("working_title must be non-empty")
    if production_status not in PRODUCTION_STATUSES:
        raise ValueError("unsupported production_status")
    try:
        json.loads(themes_json)
    except json.JSONDecodeError as exc:
        raise ValueError("themes_json must be valid JSON") from exc

    config = DatabaseConfig(
        db_path=db_path,
        migration_dir=(
            migration_dir if migration_dir is not None else default_migration_dir()
        ),
    )
    connection = open_database(config)
    repository = WorkRepository(connection)
    try:
        repository.begin_write()
        if repository.get() is not None:
            repository.rollback()
            raise WorkExistsError("WORK_EXISTS")
        repository.create(
            slug=DEFAULT_WORK_SLUG,
            working_title=normalized_title,
            genre=genre.strip(),
            premise=premise.strip(),
            themes_json=themes_json,
            description=description.strip(),
            production_status=production_status,
        )
        record = repository.get()
        if record is None:
            raise RuntimeError("work initialization failed")
        repository.commit()
        return record
    except Exception:
        repository.rollback()
        raise
    finally:
        connection.close()
