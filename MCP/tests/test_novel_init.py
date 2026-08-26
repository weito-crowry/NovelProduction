from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import build_parser, main
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database


def test_novel_init_cli_creates_exactly_one_work(tmp_path: Path) -> None:
    db_path = tmp_path / "story.db"

    exit_code = main(["--db", str(db_path), "--title", "2126"])

    assert exit_code == 0

    connection = open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )
    try:
        assert connection.execute(
            "SELECT COUNT(*), MIN(title), MAX(version) FROM works"
        ).fetchone() == (1, "2126", 1)
    finally:
        connection.close()


def test_novel_init_parser_accepts_only_db_and_title() -> None:
    parser = build_parser()

    namespace = parser.parse_args(["--db", "story.db", "--title", "2126"])

    assert namespace.db == Path("story.db")
    assert namespace.title == "2126"

    with pytest.raises(SystemExit):
        parser.parse_args(["--db", "story.db", "--title", "2126", "--slug", "x"])
