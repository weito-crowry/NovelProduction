from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from _support import initialize_test_work

from novel_core.config import DatabaseConfig
from novel_core.database import open_database
from novel_core.repositories.search_repository import SearchRepository
from novel_core.services.character_service import CharacterService
from novel_core.services.narrative_service import NarrativeService
from novel_core.services.search_service import SearchService
from novel_core.services.work_service import WorkService
from novel_core.services.world_fact_service import WorldFactService


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
    connection = open_test_database(db_path)
    try:
        initialize_test_work(connection, "2126")
        yield connection
    finally:
        connection.close()


def test_japanese_search_matches_substring_and_has_stable_order(
    database: sqlite3.Connection,
) -> None:
    service = SearchService(database)
    world_facts = WorldFactService(database)
    first = world_facts.create("国家AIが火山異常を検知")
    second = world_facts.create("火山異常は翌日に公表された")
    rows = service.search_world_facts("山異常", 30)
    assert rows == (first, second)


def test_search_is_scoped_and_bounded(database: sqlite3.Connection) -> None:
    world_facts = WorldFactService(database)
    service = SearchService(database)
    first = world_facts.create("火山異常 一号")
    second = world_facts.create("火山異常 二号")
    database.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)", ("other", "other")
    )
    other_work_id = database.execute(
        "SELECT id FROM works WHERE slug = ?", ("other",)
    ).fetchone()[0]
    database.execute(
        "INSERT INTO world_facts "
        "(work_id, topic_key, category, title, statement, details_json, canon_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (other_work_id, "other", "history", "別作品", "火山異常 別作品", "{}", "draft"),
    )
    database.commit()
    assert service.search_world_facts("", 10) == ()
    assert service.search_world_facts("火山異常", 1) == (first,)
    assert service.search_world_facts("火山異常", 10) == (first, second)


def test_fallback_search_escapes_like_wildcards(database: sqlite3.Connection) -> None:
    world_facts = WorldFactService(database)
    literal = world_facts.create("成功率100%_を記録")
    world_facts.create("成功率100を記録")
    service = SearchService(database, force_fallback=True)
    assert service.search_world_facts("100%_", 10) == (literal,)
    diagnostic = service.diagnose_world_facts("100%_", 10)
    assert diagnostic.strategy == "parameterized_like"


def test_trigram_available_path_is_diagnostic(database: sqlite3.Connection) -> None:
    repository = SearchRepository(database)
    if not repository.supports_trigram:
        pytest.skip("SQLite build does not provide FTS5 trigram")
    service = SearchService(database)
    WorldFactService(database).create("火山異常を観測")
    diagnostic = service.diagnose_world_facts("火山異常", 10)
    assert diagnostic.strategy == "fts5_trigram"
    assert diagnostic.match_count == 1


def test_character_search_matches_name_or_description_and_fallback(
    database: sqlite3.Connection,
) -> None:
    characters = CharacterService(database)
    name_match = characters.create("火星の主人公", "赤い都市")
    profile_match = characters.create("師匠", "主人公を導く")
    service = SearchService(database, force_fallback=True)
    assert service.search_characters("主人公", 10) == (name_match, profile_match)


def test_search_limit_is_bounded(database: sqlite3.Connection) -> None:
    world_facts = WorldFactService(database)
    for index in range(101):
        world_facts.create(f"観測記録 {index}")
    assert (
        len(
            SearchService(database, force_fallback=True).search_world_facts(
                "観測記録", 1000
            )
        )
        == 100
    )


def _require_trigram(database: sqlite3.Connection) -> None:
    if not SearchRepository(database).supports_trigram:
        pytest.skip("SQLite build does not provide FTS5 trigram")


def test_trigram_search_then_work_update_does_not_leak_transaction(
    database: sqlite3.Connection,
) -> None:
    _require_trigram(database)
    WorldFactService(database).create("検索対象の設定")
    SearchService(database).search_world_facts("検索対象", 10)

    assert database.in_transaction is False
    updated = WorkService(database).update("updated", 1)

    assert updated.version == 2


def test_trigram_search_then_world_fact_create_does_not_leak_transaction(
    database: sqlite3.Connection,
) -> None:
    _require_trigram(database)
    SearchService(database).search_world_facts("検索対象", 10)

    assert database.in_transaction is False
    created = WorldFactService(database).create("新しい設定")

    assert created.statement == "新しい設定"


def test_trigram_search_then_chapter_create_does_not_leak_transaction(
    database: sqlite3.Connection,
) -> None:
    _require_trigram(database)
    SearchService(database).search_world_facts("検索対象", 10)

    assert database.in_transaction is False
    created = NarrativeService(database).create_chapter("新しい章")

    assert created.title == "新しい章"


def test_trigram_search_preserves_caller_transaction_ownership(
    database: sqlite3.Connection,
) -> None:
    _require_trigram(database)
    database.execute("BEGIN IMMEDIATE")
    database.execute(
        "INSERT INTO world_facts "
        "(work_id, topic_key, title, statement) VALUES (?, ?, ?, ?)",
        (1, "outer", "外側transaction", "外側transaction検索対象"),
    )

    SearchService(database).search_world_facts("外側transaction", 10)

    assert database.in_transaction is True
    database.rollback()
    assert database.in_transaction is False
    assert (
        database.execute(
            "SELECT COUNT(*) FROM world_facts WHERE topic_key = ?", ("outer",)
        ).fetchone()[0]
        == 0
    )
