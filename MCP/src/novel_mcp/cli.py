from __future__ import annotations

import argparse
from pathlib import Path

from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import WorkExistsError
from novel_mcp.repositories.work_repository import WorkRecord, WorkRepository

DEFAULT_WORK_SLUG = "main"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--title", required=True)
    return parser


def initialize_work(db_path: Path, title: str) -> WorkRecord:
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("title must be non-empty")

    connection = open_database(_build_database_config(db_path))
    try:
        repository = WorkRepository(connection)
        repository.begin_write()
        if repository.get() is not None:
            repository.rollback()
            raise WorkExistsError("WORK_EXISTS")
        repository.create(
            slug=DEFAULT_WORK_SLUG,
            title=normalized_title,
            description=None,
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
    initialize_work(args.db, args.title)
    return 0


def _build_database_config(db_path: Path) -> DatabaseConfig:
    return DatabaseConfig(
        db_path=db_path,
        migration_dir=Path(__file__).resolve().parents[2] / "migrations",
    )
