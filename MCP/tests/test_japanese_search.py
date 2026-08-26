from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.services.character_service import CharacterService
from novel_mcp.services.search_service import SearchService
from novel_mcp.services.world_fact_service import WorldFactService


def open_test_database(db_path: Path) -> sqlite3.Connection:
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def database(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)
    try:
        yield connection
    finally:
        connection.close()


def test_japanese_search_matches_text_and_has_stable_order(
    database: sqlite3.Connection,
) -> None:
    service = SearchService(database)
    first = WorldFactService(database).create("国家AIが火山異常を検知", None, None)
    second = WorldFactService(database).create("火山異常は翌日に公表された", None, None)

    rows = service.search_world_facts("火山異常", limit=30)

    assert [row.statement for row in rows] == [first.statement, second.statement]


def test_search_is_scoped_empty_query_and_bounded(database: sqlite3.Connection) -> None:
    world_facts = WorldFactService(database)
    service = SearchService(database)
    first = world_facts.create("火山異常 一号", None, None)
    second = world_facts.create("火山異常 二号", None, None)
    database.execute(
        "INSERT INTO works (slug, title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = database.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    database.execute(
        "INSERT INTO world_facts "
        "(work_id, fact_key, title, body, canon_status) VALUES (?, ?, ?, ?, ?)",
        (other_work_id, "other", "火山異常 別作品", "火山異常 別作品", "draft"),
    )
    database.commit()

    assert service.search_world_facts("", limit=10) == ()
    assert service.search_world_facts("火山異常", limit=1) == (first,)
    assert service.search_world_facts("火山異常", limit=10) == (first, second)


def test_search_treats_like_wildcards_as_literal_and_caps_limit(
    database: sqlite3.Connection,
) -> None:
    world_facts = WorldFactService(database)
    literal = world_facts.create("成功率100%を記録", None, None)
    world_facts.create("成功率100を記録", None, None)
    for index in range(101):
        world_facts.create(f"観測記録 {index}", None, None)

    service = SearchService(database)

    assert service.search_world_facts("100%", limit=10) == (literal,)
    assert len(service.search_world_facts("観測記録", limit=1000)) == 100


def test_character_search_matches_name_or_profile(database: sqlite3.Connection) -> None:
    service = SearchService(database)
    characters = CharacterService(database)
    name_match = characters.create("火星の主人公", "赤い都市")
    profile_match = characters.create("師匠", "主人公を導く")

    assert service.search_characters("主人公", limit=10) == (name_match, profile_match)


def test_character_search_is_scoped_to_configured_work(
    database: sqlite3.Connection,
) -> None:
    service = SearchService(database)
    characters = CharacterService(database)
    own = characters.create("火星の主人公", "赤い都市")
    database.execute(
        "INSERT INTO works (slug, title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = database.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    database.execute(
        "INSERT INTO characters "
        "(work_id, character_key, display_name, summary, canon_status) "
        "VALUES (?, ?, ?, ?, ?)",
        (other_work_id, "other", "別の主人公", "別作品", "draft"),
    )
    database.commit()

    assert service.search_characters("主人公", limit=10) == (own,)


def test_search_diagnostic_reports_parameterized_like_strategy(
    database: sqlite3.Connection,
) -> None:
    world_facts = WorldFactService(database)
    world_facts.create("火山異常を観測", None, None)

    diagnostic = SearchService(database).diagnose_world_facts("火山異常", limit=10)

    assert diagnostic.strategy == "parameterized_like"
    assert diagnostic.match_count == 1
    assert diagnostic.rows[0].statement == "火山異常を観測"
