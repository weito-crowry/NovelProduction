from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import WorkExistsError
from novel_mcp.repositories.work_repository import WorkRecord, WorkRepository
from novel_mcp.services.work_service import PRODUCTION_STATUSES

DEFAULT_WORK_SLUG = "main"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--working-title", "--title", dest="working_title", required=True
    )
    parser.add_argument("--genre", default="")
    parser.add_argument("--premise", default="")
    parser.add_argument("--themes-json", default="{}")
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--production-status", choices=sorted(PRODUCTION_STATUSES), default="planned"
    )
    return parser


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
) -> WorkRecord:
    normalized_title = (
        working_title if working_title is not None else title or ""
    ).strip()
    if not normalized_title:
        raise ValueError("working_title must be non-empty")
    if production_status not in PRODUCTION_STATUSES:
        raise ValueError("unsupported production_status")
    # Reuse the service's JSON validation without opening a second database.
    try:
        json.loads(themes_json)
    except json.JSONDecodeError as exc:
        raise ValueError("themes_json must be valid JSON") from exc

    connection = open_database(_build_database_config(db_path))
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    initialize_work(
        args.db,
        working_title=args.working_title,
        genre=args.genre,
        premise=args.premise,
        themes_json=args.themes_json,
        description=args.description,
        production_status=args.production_status,
    )
    return 0


def _build_database_config(db_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=db_path,
        migration_dir=Path(__file__).resolve().parents[2] / "migrations",
    )
