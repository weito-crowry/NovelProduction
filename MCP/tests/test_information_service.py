from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import ValidationError, VersionConflictError
from novel_mcp.services.information_service import InformationService


def open_test_database(db_path: Path):
    return open_database(
        DatabaseConfig(
            db_path=db_path,
            migration_dir=Path(__file__).resolve().parents[1] / "migrations",
        )
    )


@pytest.fixture
def service(tmp_path: Path):
    db_path = tmp_path / "story.db"
    initialize_work(db_path, "2126")
    connection = open_test_database(db_path)
    try:
        yield InformationService(connection)
    finally:
        connection.close()


def test_information_persists_truth_guard_and_notes_json(
    service: InformationService,
) -> None:
    item = service.create_information(
        "国家AIは誤認した",
        truth_status="false",
        authoring_guard="主人公はまだ知らない",
        notes_json={"source": "draft"},
        importance=2,
    )

    fetched = service.get_information(item.id)

    assert fetched == item
    assert fetched.truth_status == "false"
    assert fetched.authoring_guard == "主人公はまだ知らない"
    assert fetched.notes_json == '{"source":"draft"}'
    assert fetched.importance == 2


def test_information_update_uses_optimistic_locking(
    service: InformationService,
) -> None:
    item = service.create_information("旧い情報", truth_status="uncertain")
    updated = service.update_information(
        item.id, expected_version=item.version, statement="新しい情報"
    )

    assert (updated.statement, updated.version) == ("新しい情報", 2)
    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.update_information(
            item.id, expected_version=item.version, statement="競合"
        )


def test_information_search_is_bounded_and_escapes_like_wildcards(
    service: InformationService,
) -> None:
    literal = service.create_information("成功率100%_を記録")
    service.create_information("成功率100を記録")

    assert service.search_information("100%_", limit=100) == (literal,)
    assert service.search_information("", limit=10) == ()
    with pytest.raises(ValidationError, match="limit"):
        service.search_information("記録", limit=101)


def test_information_rejects_invalid_truth_json_and_importance(
    service: InformationService,
) -> None:
    with pytest.raises(ValidationError, match="truth_status"):
        service.create_information("情報", truth_status="known")
    with pytest.raises(ValidationError, match="notes_json"):
        service.create_information("情報", notes_json="not-json")
    with pytest.raises(ValidationError, match="importance"):
        service.create_information("情報", importance=-1)
