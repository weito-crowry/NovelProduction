from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from novel_core.style_analysis.entity_models import ALIAS_KINDS, ENTITY_TYPES
from novel_core.style_analysis.semantic_models import (
    BLOCK_PRIMARY_LABELS,
    POV_MODES,
    SCENE_FUNCTIONS,
    SCENE_INFORMATION_LOADS,
    SCENE_INTERACTIONS,
    SCENE_PACES,
    SCENE_TONES,
)
from novel_core.style_analysis.term_models import NOVELTY_VALUES, TERM_TYPES

REVIEW_ITEM_SUBJECT_TYPES = frozenset(
    {
        "structure_revision",
        "scene",
        "block",
        "mention",
        "term_mention",
        "entity",
        "term",
    }
)
INFERENCE_REVIEW_FIELDS: Mapping[tuple[str, str], str] = {
    ("mention", "mention.entity_resolution"): "mention.entity_resolution",
    ("block", "block.speaker"): "speaker",
    ("block", "block.semantic_primary"): "block.semantic_primary",
    ("term", "term.novelty"): "term.novelty",
    ("term_mention", "term_mention.explanation"): "term_explanation",
    ("scene", "scene.function"): "scene.function",
    ("scene", "scene.tone"): "scene.tone",
    ("scene", "scene.pace"): "scene.pace",
    ("scene", "scene.information_load"): "scene.information_load",
    ("scene", "scene.interaction"): "scene.interaction",
    ("scene", "scene.pov"): "scene.pov",
    ("entity_alias", "entity_alias.acceptance"): "alias",
    ("term_alias", "term_alias.acceptance"): "alias",
}
INFERENCE_ANALYZERS: Mapping[str, str] = {
    "mention.entity_resolution": "entity-resolver",
    "speaker": "speaker-attribution",
    "block.semantic_primary": "block-semantic-classifier",
    "term.novelty": "term-resolver",
    "term_explanation": "term-explanation-detector",
    "scene.function": "scene-semantic-classifier",
    "scene.tone": "scene-semantic-classifier",
    "scene.pace": "scene-semantic-classifier",
    "scene.information_load": "scene-semantic-classifier",
    "scene.interaction": "scene-semantic-classifier",
    "scene.pov": "pov-classifier",
}
OVERRIDE_FIELDS: Mapping[str, frozenset[str]] = {
    "block": frozenset(("block.speaker_entity_id", "block.semantic_primary")),
    "mention": frozenset(("mention.entity_id",)),
    "entity": frozenset(
        ("entity.enabled", "entity.canonical_name", "entity.entity_type")
    ),
    "term": frozenset(
        ("term.enabled", "term.canonical_label", "term.term_type", "term.novelty")
    ),
    "term_mention": frozenset(("term_mention.sufficient_explanation_annotation_id",)),
    "scene": frozenset(
        (
            "scene.function",
            "scene.tone",
            "scene.pace",
            "scene.information_load",
            "scene.interaction",
            "scene.pov_mode",
            "scene.pov_entity_id",
        )
    ),
}
STRUCTURE_SUBJECTS = frozenset(("scene", "block", "mention", "term_mention"))
CLEARABLE_FIELDS = frozenset(
    (
        "block.speaker_entity_id",
        "mention.entity_id",
        "term_mention.sufficient_explanation_annotation_id",
        "scene.pov_entity_id",
    )
)


@dataclass(frozen=True, slots=True)
class SubjectInfo:
    document_id: int | None
    reference_work_id: int | None
    structure_revision_id: int | None
    start_cp: int | None = None
    end_cp: int | None = None
    block_id: int | None = None

    @property
    def scope(self) -> tuple[str, int]:
        if self.document_id is not None:
            return "document_id", self.document_id
        if self.reference_work_id is not None:
            return "reference_work_id", self.reference_work_id
        raise ValueError("REVIEW_SCOPE_INVALID")


__all__ = [
    "ALIAS_KINDS",
    "BLOCK_PRIMARY_LABELS",
    "CLEARABLE_FIELDS",
    "ENTITY_TYPES",
    "INFERENCE_ANALYZERS",
    "INFERENCE_REVIEW_FIELDS",
    "NOVELTY_VALUES",
    "OVERRIDE_FIELDS",
    "POV_MODES",
    "REVIEW_ITEM_SUBJECT_TYPES",
    "SCENE_FUNCTIONS",
    "SCENE_INFORMATION_LOADS",
    "SCENE_INTERACTIONS",
    "SCENE_PACES",
    "SCENE_TONES",
    "STRUCTURE_SUBJECTS",
    "SubjectInfo",
    "TERM_TYPES",
]
