from __future__ import annotations

from pathlib import Path

import pytest

from novel_mcp.cli import initialize_work
from novel_mcp.config import DatabaseConfig
from novel_mcp.database import open_database
from novel_mcp.errors import (
    CanonEntityNotFoundError,
    CanonReasonRequired,
    ValidationError,
    VersionConflictError,
)
from novel_mcp.repositories.canon_repository import CanonChange
from novel_mcp.services.canon_service import CanonService
from novel_mcp.services.world_fact_service import WorldFactService


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
        yield CanonService(connection)
    finally:
        connection.close()


def test_canon_transition_requires_reason_and_commits_decision_atomically(
    service: CanonService,
) -> None:
    fact = WorldFactService(service.connection).create("旧記述", None, None)

    with pytest.raises(CanonReasonRequired, match="CANON_REASON_REQUIRED"):
        service.set_canon_status("world_fact", fact.id, "canon", None)

    decision = service.set_canon_status("world_fact", fact.id, "canon", "採用理由")

    assert decision.changes[0].entity_id == fact.id
    assert decision.changes[0].before_payload["canon_status"] == "draft"
    assert decision.changes[0].after_payload["canon_status"] == "canon"
    assert service.connection.execute(
        "SELECT canon_status FROM world_facts WHERE id = ?", (fact.id,)
    ).fetchone() == ("canon",)


def test_canonical_content_change_requires_reason_and_records_payloads(
    service: CanonService,
) -> None:
    fact = WorldFactService(service.connection).create("旧記述", None, None)
    service.set_canon_status("world_fact", fact.id, "canon", "採用")

    with pytest.raises(CanonReasonRequired):
        service.update_content("world_fact", fact.id, {"body": "新記述"}, reason=None)

    decision = service.update_content(
        "world_fact", fact.id, {"body": "新記述"}, reason="訂正"
    )
    assert decision.changes[0].before_payload["body"] == "旧記述"
    assert decision.changes[0].after_payload["body"] == "新記述"


def test_record_decision_supports_multiple_changes_and_round_trip_search(
    service: CanonService,
) -> None:
    fact = WorldFactService(service.connection).create("旧記述", None, None)
    changes = (
        CanonChange(
            entity_type="world_fact",
            entity_id=fact.id,
            action="status_changed",
            before_payload={"canon_status": "draft"},
            after_payload={"canon_status": "canon"},
        ),
    )

    decision = service.record_decision("採用判断", "採用理由", changes)
    assert service.get_decision(decision.id) == decision
    assert service.search_decisions("採用", 10) == (decision,)
    assert service.connection.execute(
        "SELECT decision_key, decided_at FROM canon_decisions WHERE id = ?",
        (decision.id,),
    ).fetchone()[0]
    assert service.connection.execute(
        "SELECT decision_key, decided_at FROM canon_decisions WHERE id = ?",
        (decision.id,),
    ).fetchone()[1]


def test_invalid_status_and_missing_entity_are_structured_errors(
    service: CanonService,
) -> None:
    with pytest.raises(ValidationError, match="VALIDATION_ERROR"):
        service.set_canon_status("world_fact", 1, "unknown", "理由")
    with pytest.raises(CanonEntityNotFoundError) as error:
        service.set_canon_status("world_fact", 9999, "canon", "理由")
    assert error.value.code == "NOT_FOUND"


def test_status_change_snapshots_inside_transaction_and_uses_version_cas(
    service: CanonService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fact = WorldFactService(service.connection).create("旧記述", None, None)
    original_get = service.repository.get_entity
    original_update = service.repository.update_status
    observed: dict[str, object] = {}

    def get_entity(**kwargs):
        observed["in_transaction"] = service.connection.in_transaction
        record = original_get(**kwargs)
        if record is not None:
            service.connection.execute(
                "UPDATE world_facts SET version = version + 1 WHERE id = ?",
                (fact.id,),
            )
        return record

    def update_status(**kwargs):
        observed["expected_version"] = kwargs["expected_version"]
        return original_update(**kwargs)

    monkeypatch.setattr(service.repository, "get_entity", get_entity)
    monkeypatch.setattr(service.repository, "update_status", update_status)

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.set_canon_status("world_fact", fact.id, "canon", "採用")

    assert observed == {"in_transaction": True, "expected_version": 1}
    assert service.connection.execute(
        "SELECT canon_status, version FROM world_facts WHERE id = ?", (fact.id,)
    ).fetchone() == ("draft", 1)


def test_content_change_snapshots_inside_transaction_and_uses_version_cas(
    service: CanonService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fact = WorldFactService(service.connection).create("旧記述", None, None)
    original_get = service.repository.get_entity
    original_update = service.repository.update_content
    observed: dict[str, object] = {}

    def get_entity(**kwargs):
        observed["in_transaction"] = service.connection.in_transaction
        record = original_get(**kwargs)
        if record is not None:
            service.connection.execute(
                "UPDATE world_facts SET version = version + 1 WHERE id = ?",
                (fact.id,),
            )
        return record

    def update_content(**kwargs):
        observed["expected_version"] = kwargs["expected_version"]
        return original_update(**kwargs)

    monkeypatch.setattr(service.repository, "get_entity", get_entity)
    monkeypatch.setattr(service.repository, "update_content", update_content)

    with pytest.raises(VersionConflictError, match="VERSION_CONFLICT"):
        service.update_content("world_fact", fact.id, {"body": "新記述"}, reason=None)

    assert observed == {"in_transaction": True, "expected_version": 1}
    assert service.connection.execute(
        "SELECT body, version FROM world_facts WHERE id = ?", (fact.id,)
    ).fetchone() == ("旧記述", 1)


def test_failed_decision_insert_rolls_back_target_mutation(
    service: CanonService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fact = WorldFactService(service.connection).create("旧記述", None, None)
    original = service.repository.insert_decision

    def fail(*args, **kwargs):
        raise RuntimeError("decision insert failed")

    monkeypatch.setattr(service.repository, "insert_decision", fail)
    with pytest.raises(RuntimeError, match="decision insert failed"):
        service.set_canon_status("world_fact", fact.id, "canon", "採用")

    assert service.connection.execute(
        "SELECT canon_status FROM world_facts WHERE id = ?", (fact.id,)
    ).fetchone() == ("draft",)
    monkeypatch.setattr(service.repository, "insert_decision", original)
