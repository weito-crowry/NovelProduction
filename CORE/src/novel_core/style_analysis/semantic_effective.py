from __future__ import annotations

import sqlite3

from novel_core.style_analysis.entity_models import ENTITY_TYPES
from novel_core.style_analysis.semantic_metric_support import (
    EffectiveValue,
    latest_override,
)
from novel_core.style_analysis.semantic_values import json_field
from novel_core.style_analysis.term_models import TERM_TYPES


def resolve_entity_enabled(
    connection: sqlite3.Connection, entity_id: int
) -> EffectiveValue:
    row = connection.execute(
        "SELECT id FROM style_entities WHERE id = ?", (entity_id,)
    ).fetchone()
    if row is None:
        return EffectiveValue(None, "unknown")
    override = latest_override(connection, "entity", entity_id, "entity.enabled")
    if override is not None and override[1] == "set":
        value = json_field(override[2], "value")
        if isinstance(value, bool):
            return EffectiveValue(value, "manual", override_id=override[0])
        return EffectiveValue(None, "unknown", override_id=override[0])
    return EffectiveValue(True, "default")


def resolve_entity_name(
    connection: sqlite3.Connection, entity_id: int
) -> EffectiveValue:
    row = connection.execute(
        "SELECT canonical_name FROM style_entities WHERE id = ?", (entity_id,)
    ).fetchone()
    if row is None:
        return EffectiveValue(None, "unknown")
    override = latest_override(connection, "entity", entity_id, "entity.canonical_name")
    if override is not None and override[1] == "set":
        value = json_field(override[2], "value")
        if isinstance(value, str) and value:
            return EffectiveValue(value, "manual", override_id=override[0])
        return EffectiveValue(None, "unknown", override_id=override[0])
    return EffectiveValue(str(row[0]), "inferred")


def resolve_entity_type(
    connection: sqlite3.Connection, entity_id: int
) -> EffectiveValue:
    row = connection.execute(
        "SELECT entity_type FROM style_entities WHERE id = ?", (entity_id,)
    ).fetchone()
    if row is None:
        return EffectiveValue(None, "unknown")
    override = latest_override(connection, "entity", entity_id, "entity.entity_type")
    if override is not None and override[1] == "set":
        value = json_field(override[2], "value")
        valid = isinstance(value, str) and value in ENTITY_TYPES
        return EffectiveValue(
            value if valid else None,
            "manual" if valid else "unknown",
            override_id=override[0],
        )
    value = row[0]
    valid = isinstance(value, str) and value in ENTITY_TYPES
    return EffectiveValue(
        value if valid else None,
        "inferred" if valid else "unknown",
        override_id=override[0] if override is not None else None,
    )


def resolve_term_enabled(
    connection: sqlite3.Connection, term_id: int
) -> EffectiveValue:
    row = connection.execute(
        "SELECT id FROM style_terms WHERE id = ?", (term_id,)
    ).fetchone()
    if row is None:
        return EffectiveValue(None, "unknown")
    override = latest_override(connection, "term", term_id, "term.enabled")
    if override is not None and override[1] == "set":
        value = json_field(override[2], "value")
        if isinstance(value, bool):
            return EffectiveValue(value, "manual", override_id=override[0])
        return EffectiveValue(None, "unknown", override_id=override[0])
    return EffectiveValue(True, "default")


def resolve_term_label(connection: sqlite3.Connection, term_id: int) -> EffectiveValue:
    row = connection.execute(
        "SELECT canonical_label FROM style_terms WHERE id = ?", (term_id,)
    ).fetchone()
    if row is None:
        return EffectiveValue(None, "unknown")
    override = latest_override(connection, "term", term_id, "term.canonical_label")
    if override is not None and override[1] == "set":
        value = json_field(override[2], "value")
        if isinstance(value, str) and value:
            return EffectiveValue(value, "manual", override_id=override[0])
        return EffectiveValue(None, "unknown", override_id=override[0])
    return EffectiveValue(str(row[0]), "inferred")


def resolve_term_type(connection: sqlite3.Connection, term_id: int) -> EffectiveValue:
    row = connection.execute(
        "SELECT term_type FROM style_terms WHERE id = ?", (term_id,)
    ).fetchone()
    if row is None:
        return EffectiveValue(None, "unknown")
    override = latest_override(connection, "term", term_id, "term.term_type")
    if override is not None and override[1] == "set":
        value = json_field(override[2], "value")
        valid = isinstance(value, str) and value in TERM_TYPES
        return EffectiveValue(
            value if valid else None,
            "manual" if valid else "unknown",
            override_id=override[0],
        )
    value = row[0]
    valid = isinstance(value, str) and value in TERM_TYPES
    return EffectiveValue(
        value if valid else None,
        "inferred" if valid else "unknown",
    )
