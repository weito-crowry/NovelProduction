from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EntityRecord:
    id: int
    reference_work_id: int | None
    document_id: int | None
    entity_type: str
    canonical_name: str
    origin: str
    created_by_run_id: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class EntityAliasRecord:
    id: int
    entity_id: int
    alias: str
    alias_kind: str
    origin: str
    analysis_run_id: int | None
    source_mention_id: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class MentionRecord:
    id: int
    structure_revision_id: int
    scene_id: int
    block_id: int
    start_cp: int
    end_cp: int
    surface: str
    mention_type: str
    entity_type_candidate: str
    canonical_name_candidate: str
    confidence: float
    analysis_run_id: int


ENTITY_TYPES = frozenset(
    {
        "person",
        "organization",
        "location",
        "technology",
        "concept",
        "product",
        "event",
        "other",
    }
)
MENTION_TYPES = frozenset({"proper_name", "alias", "pronoun", "role_title"})
ALIAS_KINDS = frozenset({"name", "surname", "given_name", "nickname", "title", "role"})
