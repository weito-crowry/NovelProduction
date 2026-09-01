import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_style_analysis_migration import open_test_database

from novel_core.errors import ValidationError
from novel_core.style_analysis.structure_service import StyleStructureService
from novel_core.style_analysis.text_service import StyleTextService


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    database = open_test_database(tmp_path / "story.db")
    try:
        yield database
    finally:
        database.close()


def insert_project_episode(connection: sqlite3.Connection, position: int) -> int:
    connection.execute(
        "INSERT INTO works (slug, working_title) VALUES (?, ?)",
        (f"style-{position}", f"Style {position}"),
    )
    work_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.execute(
        "INSERT INTO chapters (work_id, position, title) VALUES (?, 1, ?)",
        (work_id, f"Chapter {position}"),
    )
    chapter_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.execute(
        "INSERT INTO episodes (work_id, chapter_id, position, title) "
        "VALUES (?, ?, ?, ?)",
        (work_id, chapter_id, position, f"Episode {position}"),
    )
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def insert_style_document(connection: sqlite3.Connection, *, episode_id: int) -> int:
    episode = connection.execute(
        "SELECT work_id FROM episodes WHERE id = ?", (episode_id,)
    ).fetchone()
    assert episode is not None
    connection.execute(
        "INSERT INTO style_documents "
        "(kind, project_work_id, project_episode_id) VALUES (?, ?, ?)",
        ("project_episode_draft", episode[0], episode_id),
    )
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def insert_text_revision(
    connection: sqlite3.Connection, *, document_id: int, revision_no: int
) -> int:
    digest = f"{revision_no:064x}"
    connection.execute(
        "INSERT INTO style_text_revisions "
        "(document_id, revision_no, project_draft_id, raw_text, canonical_text, "
        "raw_sha256, canonical_sha256, normalization_input_fingerprint, "
        "normalizer_id, normalizer_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            document_id,
            revision_no,
            revision_no,
            f"raw {revision_no}",
            f"canonical {revision_no}",
            digest,
            digest,
            digest,
            "test-normalizer",
            1,
        ),
    )
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def insert_structure_revision(
    connection: sqlite3.Connection,
    *,
    text_revision_id: int,
    revision_no: int = 1,
    source_kind: str = "automatic",
) -> int:
    digest = f"{text_revision_id + revision_no:064x}"
    connection.execute(
        "INSERT INTO style_structure_revisions "
        "(text_revision_id, revision_no, segmenter_id, segmenter_version, "
        "source_kind, fingerprint) VALUES (?, ?, ?, ?, ?, ?)",
        (text_revision_id, revision_no, "test-segmenter", 1, source_kind, digest),
    )
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def current_pointers(
    connection: sqlite3.Connection, document_id: int
) -> tuple[int | None, int | None]:
    return connection.execute(
        "SELECT current_text_revision_id, current_structure_revision_id "
        "FROM style_documents WHERE id = ?",
        (document_id,),
    ).fetchone()


def test_current_text_change_clears_structure_only_when_changed(
    connection: sqlite3.Connection,
) -> None:
    episode_id = insert_project_episode(connection, 1)
    document_id = insert_style_document(connection, episode_id=episode_id)
    first_text = insert_text_revision(
        connection, document_id=document_id, revision_no=1
    )
    second_text = insert_text_revision(
        connection, document_id=document_id, revision_no=2
    )
    first_structure = insert_structure_revision(connection, text_revision_id=first_text)
    second_structure = insert_structure_revision(
        connection, text_revision_id=second_text
    )
    connection.commit()
    text_service = StyleTextService(connection)
    structure_service = StyleStructureService(connection)

    text_service.set_current_text(document_id, first_text)
    structure_service.set_current_structure(document_id, first_structure)
    assert current_pointers(connection, document_id) == (first_text, first_structure)

    text_service.set_current_text(document_id, second_text)
    assert current_pointers(connection, document_id) == (second_text, None)

    structure_service.set_current_structure(document_id, second_structure)
    text_service.set_current_text(document_id, second_text)
    assert current_pointers(connection, document_id) == (second_text, second_structure)


def test_same_document_current_structure_succeeds(
    connection: sqlite3.Connection,
) -> None:
    episode_id = insert_project_episode(connection, 1)
    document_id = insert_style_document(connection, episode_id=episode_id)
    text_revision_id = insert_text_revision(
        connection, document_id=document_id, revision_no=1
    )
    structure_revision_id = insert_structure_revision(
        connection, text_revision_id=text_revision_id
    )
    connection.commit()

    StyleTextService(connection).set_current_text(document_id, text_revision_id)
    StyleStructureService(connection).set_current_structure(
        document_id, structure_revision_id
    )

    assert current_pointers(connection, document_id) == (
        text_revision_id,
        structure_revision_id,
    )


def test_current_structure_must_belong_to_current_text_revision(
    connection: sqlite3.Connection,
) -> None:
    episode_id = insert_project_episode(connection, 1)
    document_id = insert_style_document(connection, episode_id=episode_id)
    first_text = insert_text_revision(
        connection, document_id=document_id, revision_no=1
    )
    second_text = insert_text_revision(
        connection, document_id=document_id, revision_no=2
    )
    first_structure = insert_structure_revision(connection, text_revision_id=first_text)
    connection.commit()
    StyleTextService(connection).set_current_text(document_id, second_text)

    with pytest.raises(ValidationError, match="CURRENT_STRUCTURE_TEXT_MISMATCH"):
        StyleStructureService(connection).set_current_structure(
            document_id, first_structure
        )

    assert current_pointers(connection, document_id) == (second_text, None)


def test_current_structure_must_belong_to_same_document(
    connection: sqlite3.Connection,
) -> None:
    first_episode = insert_project_episode(connection, 1)
    second_episode = insert_project_episode(connection, 2)
    first_document = insert_style_document(connection, episode_id=first_episode)
    second_document = insert_style_document(connection, episode_id=second_episode)
    first_text = insert_text_revision(
        connection, document_id=first_document, revision_no=1
    )
    second_text = insert_text_revision(
        connection, document_id=second_document, revision_no=1
    )
    second_structure = insert_structure_revision(
        connection, text_revision_id=second_text
    )
    connection.commit()
    StyleTextService(connection).set_current_text(first_document, first_text)

    with pytest.raises(ValidationError, match="STRUCTURE_REVISION_DOCUMENT_MISMATCH"):
        StyleStructureService(connection).set_current_structure(
            first_document, second_structure
        )

    assert current_pointers(connection, first_document) == (first_text, None)


def test_historical_selection_does_not_mutate_pointer(
    connection: sqlite3.Connection,
) -> None:
    episode_id = insert_project_episode(connection, 1)
    document_id = insert_style_document(connection, episode_id=episode_id)
    first_text = insert_text_revision(
        connection, document_id=document_id, revision_no=1
    )
    second_text = insert_text_revision(
        connection, document_id=document_id, revision_no=2
    )
    first_structure = insert_structure_revision(connection, text_revision_id=first_text)
    connection.commit()
    second_structure = insert_structure_revision(
        connection, text_revision_id=second_text
    )
    connection.commit()
    text_service = StyleTextService(connection)
    structure_service = StyleStructureService(connection)
    text_service.set_current_text(document_id, second_text)
    structure_service.set_current_structure(document_id, second_structure)

    historical_text = text_service.get_text_revision(document_id, first_text)
    historical_structure = structure_service.get_structure_revision(
        document_id, first_structure
    )

    assert historical_text.id == first_text
    assert historical_structure.id == first_structure
    assert current_pointers(connection, document_id) == (second_text, second_structure)


def test_structure_read_preserves_manual_and_semantic_source_kind(
    connection: sqlite3.Connection,
) -> None:
    episode_id = insert_project_episode(connection, 1)
    document_id = insert_style_document(connection, episode_id=episode_id)
    text_revision_id = insert_text_revision(
        connection, document_id=document_id, revision_no=1
    )
    manual_structure = insert_structure_revision(
        connection,
        text_revision_id=text_revision_id,
        source_kind="manual",
    )
    semantic_structure = insert_structure_revision(
        connection,
        text_revision_id=text_revision_id,
        revision_no=2,
        source_kind="semantic",
    )
    connection.commit()
    StyleTextService(connection).set_current_text(document_id, text_revision_id)
    service = StyleStructureService(connection)

    manual_record = service.get_structure_revision(document_id, manual_structure)
    assert manual_record.source_kind == "manual"
    service.set_current_structure(document_id, semantic_structure)
    semantic_record = service.get_structure_revision(document_id, semantic_structure)
    assert semantic_record.source_kind == "semantic"
