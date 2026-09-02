from __future__ import annotations

from typing import Any, cast

from novel_core.style_analysis.analyzers.common import split_blocks
from novel_core.style_analysis.fingerprints import JsonValue
from novel_core.style_analysis.model_contracts import JsonObject
from novel_core.style_analysis.resolver_candidates import build_identity_shortlist
from novel_core.style_analysis.resumable_models import (
    DocumentAnalysisRequest,
    PreparedModelCall,
    ResumableStageHost,
)


class ResumableStructureStagesMixin(ResumableStageHost):
    def _boundary_call(self, state: dict[str, Any]) -> PreparedModelCall | None:
        structure_id = int(state["structure_revision_id"])
        run_id = self._ensure_run(
            state, "scene-boundary-detector", "style.scene_boundary"
        )
        if state.pop("stage_reused", False):
            state["stage"] = "structure_finalize"
            state["stage_index"] = 3
            state["subject_index"] = 0
            state["chunk_index"] = 0
            return None
        if state.get("stage_errors"):
            self._finish_stage(state, run_id)
            state["subject_index"] = 0
            state["chunk_index"] = 0
            state["stage"] = "structure_finalize"
            state["stage_index"] = 3
            return None
        scenes = self.structure.list_scenes(structure_id)
        blocks = self.structure.list_blocks(structure_id)
        revision = self.text.get_text_revision(
            int(state["document_id"]), int(state["text_revision_id"])
        )
        scene_index = int(state.get("subject_index", 0))
        while scene_index < len(scenes):
            self.checkpoint()
            scene = scenes[scene_index]
            state["stage_scene_id"] = scene.id
            values = [
                self._block_json(block, revision.canonical_text)
                for block in blocks
                if block.scene_id == scene.id
            ]
            chunks = split_blocks(values)
            chunk_index = int(state.get("chunk_index", 0))
            if len(values) >= 2 and chunk_index < len(chunks):
                call_key = (
                    f"scene-boundary-detector:scene:{scene.id}:chunk:{chunk_index}"
                )
                payload: JsonObject = {
                    "base_structure_revision_id": structure_id,
                    "scene_id": scene.id,
                    "blocks": cast(JsonValue, chunks[chunk_index]),
                }
                state["pending_call_key"] = call_key
                state["current_payload"] = payload
                return self._prepared(
                    call_key,
                    run_id,
                    "scene-boundary-detector",
                    "style.scene_boundary",
                    "style.scene_boundary.v1",
                    payload,
                )
            scene_index += 1
            state["subject_index"] = scene_index
            state["chunk_index"] = 0
            state["stage_responses"] = []
        self._finish_stage(state, run_id)
        state["subject_index"] = 0
        state["chunk_index"] = 0
        state["stage"] = "structure_finalize"
        state["stage_index"] = 3
        return None

    def _prepare_structure(
        self, request: DocumentAnalysisRequest, state: dict[str, Any]
    ) -> None:
        document = self.text.get_document(request.document_id)
        if document is None:
            raise ValueError("STYLE_DOCUMENT_NOT_FOUND")
        revision = self.text.get_text_revision(
            request.document_id, request.text_revision_id
        )
        structure_id: int | None
        if request.structure_revision_id is not None:
            structure_id = request.structure_revision_id
        elif (
            not request.rebuild_structure
            and document.current_text_revision_id == revision.id
        ):
            structure_id = document.current_structure_revision_id
        else:
            structure_id = None
        built_structure = structure_id is None
        if structure_id is None:
            structure_id = self.structure.build_automatic_structure(
                document_id=request.document_id,
                text_revision_id=revision.id,
                set_current=False,
            ).id
        structure = self.structure.get_structure_revision(
            request.document_id, structure_id
        )
        if structure.text_revision_id != revision.id:
            raise ValueError("STRUCTURE_TEXT_REVISION_MISMATCH")
        state["structure_revision_id"] = structure.id
        state["target_was_current_text"] = (
            document.current_text_revision_id == revision.id
        )
        state["initial_current_text_revision_id"] = document.current_text_revision_id
        state["initial_current_structure_revision_id"] = (
            document.current_structure_revision_id
        )
        state["pointer_update_allowed"] = built_structure and (
            document.current_text_revision_id == revision.id
            and request.structure_revision_id is None
        )
        if (
            request.preset == "full"
            and request.structure_revision_id is None
            and structure.source_kind == "automatic"
        ):
            state["stage"] = "scene_boundary"
            state["stage_index"] = 2
        else:
            stage = self._first_non_boundary_stage(request.preset)
            state["stage"] = stage
            state["stage_index"] = self._stage_order.index(stage) + 1

    @staticmethod
    def _first_non_boundary_stage(preset: str) -> str:
        if preset == "full":
            return "entity_mentions"
        return "semantic_metrics" if preset == "metrics" else "basic_metrics"

    def _finalize_structure(self, state: dict[str, Any]) -> None:
        boundary_run = self._stage_run(state, "scene_boundary")
        if boundary_run is not None:
            structure = self.structure.materialize_semantic_structure(
                document_id=int(state["document_id"]),
                text_revision_id=int(state["text_revision_id"]),
                parent_structure_revision_id=int(state["structure_revision_id"]),
                boundary_analysis_run_id=boundary_run,
                auto_apply_threshold=self.policy.scene_boundary_auto_apply,
            )
            state["structure_revision_id"] = structure.id
            state["pointer_update_allowed"] = bool(
                state.get("target_was_current_text")
                and state.get("requested_structure_revision_id") is None
            )
        stage = self._first_non_boundary_stage(str(state.get("preset", "full")))
        state["stage"] = stage
        state["stage_index"] = self._stage_order.index(stage) + 1
        state["subject_index"] = 0
        state["chunk_index"] = 0
        state["stage_responses"] = []
        state["stage_substage"] = "classify"
        state["stage_scene_id"] = None

    def _model_stage_call(
        self, request: DocumentAnalysisRequest, state: dict[str, Any]
    ) -> PreparedModelCall | None:
        stage = cast(str, state["stage"])
        analyzer_id, prompt_id, contract_id = self._prompt_map[stage]
        run_id = self._ensure_run(state, analyzer_id, prompt_id)
        if state.pop("stage_reused", False):
            self._next_stage(state)
            return None
        if state.get("stage_errors"):
            self._finish_stage(state, run_id)
            self._next_stage(state)
            return None
        if self._dependency_failed(state, analyzer_id):
            self.runs.finish_run(
                run_id,
                status="failed",
                finished_at=None,
                error_code="DEPENDENCY_FAILED",
                error_message="DEPENDENCY_FAILED",
            )
            self._next_stage(state)
            return None
        spec = self._current_spec(stage, request, state)
        if spec is None:
            if self._complete_deterministic_subject(state, stage):
                state["subject_index"] = int(state.get("subject_index", 0)) + 1
                return None
            self._finish_stage(state, run_id)
            self._next_stage(state)
            return None
        call_key, payload, response_contract_id = spec
        state["pending_call_key"] = call_key
        state["current_payload"] = payload
        return self._prepared(
            call_key,
            run_id,
            analyzer_id,
            prompt_id,
            response_contract_id or contract_id,
            payload,
        )

    def _current_spec(
        self, stage: str, request: DocumentAnalysisRequest, state: dict[str, Any]
    ) -> tuple[str, JsonObject, str | None] | None:
        state.pop("deterministic_subject", None)
        structure_id = int(state["structure_revision_id"])
        revision = self.text.get_text_revision(
            request.document_id, request.text_revision_id
        )
        blocks = self.structure.list_blocks(structure_id)
        scenes = self.structure.list_scenes(structure_id)
        block_json = [
            self._block_json(block, revision.canonical_text) for block in blocks
        ]
        subject_index = int(state.get("subject_index", 0))
        if stage == "scene_boundary":
            if subject_index >= len(scenes):
                return None
            scene = scenes[subject_index]
            state["stage_scene_id"] = scene.id
            values = [item for item in block_json if item.get("scene_id") == scene.id]
            chunks = split_blocks(values)
            chunk_index = int(state.get("chunk_index", 0))
            if len(values) < 2 or chunk_index >= len(chunks):
                return None
            boundary_payload: JsonObject = {
                "base_structure_revision_id": structure_id,
                "scene_id": scene.id,
                "blocks": cast(JsonValue, chunks[chunk_index]),
            }
            return (
                f"scene-boundary-detector:scene:{scene.id}:chunk:{chunk_index}",
                boundary_payload,
                None,
            )
        if stage in {"entity_mentions", "term_candidates", "scene_semantics"}:
            if subject_index >= len(scenes):
                return None
            scene = scenes[subject_index]
            state["stage_scene_id"] = scene.id
            scene_blocks = [
                item for item in block_json if item.get("scene_id") == scene.id
            ]
            chunks = split_blocks(scene_blocks)
            substage = str(state.get("stage_substage", "classify"))
            chunk_index = int(state.get("chunk_index", 0))
            if stage == "scene_semantics" and substage == "reduce":
                classify_responses = [
                    cast(JsonObject, value)
                    for value in cast(list[JsonValue], state.get("stage_responses", []))
                ]
                return (
                    f"scene-semantic-classifier:scene:{scene.id}:reduce",
                    {
                        "mode": "reduce",
                        "chunks": [
                            {
                                "char_count": sum(
                                    len(str(block.get("text", ""))) for block in chunk
                                ),
                                "pace": result["pace"],
                                "information_load": result["information_load"],
                                "interaction": result["interaction"],
                            }
                            for chunk, result in zip(
                                chunks, classify_responses, strict=False
                            )
                        ],
                    },
                    "style.scene_semantics.reduce.v1",
                )
            if chunk_index >= len(chunks):
                return None
            previous = self._previous_context(block_json, scene.id)
            payload: JsonObject = {
                "scene_id": scene.id,
                "blocks": cast(JsonValue, chunks[chunk_index]),
            }
            if stage == "scene_semantics":
                payload["mode"] = "classify"
            elif stage == "entity_mentions":
                payload["previous_context_blocks"] = (
                    cast(JsonValue, previous) if chunk_index == 0 else []
                )
            return (
                f"{self._prompt_map[stage][0]}:scene:{scene.id}:chunk:{chunk_index}",
                payload,
                None,
            )
        if stage == "pov":
            if subject_index >= len(scenes):
                return None
            scene = scenes[subject_index]
            state["stage_scene_id"] = scene.id
            scene_blocks = [
                item for item in block_json if item.get("scene_id") == scene.id
            ]
            chunks = split_blocks(scene_blocks)
            people = self._people_for_scene(
                request.document_id,
                self._dependency_run_id(state, "entity-resolver"),
                scene.id,
            )
            substage = str(state.get("stage_substage", "classify"))
            chunk_index = int(state.get("chunk_index", 0))
            if substage == "reduce":
                classify_responses = [
                    cast(JsonObject, value)
                    for value in cast(list[JsonValue], state.get("stage_responses", []))
                ]
                return (
                    f"pov-classifier:scene:{scene.id}:reduce",
                    {
                        "mode": "reduce",
                        "people": cast(JsonValue, people),
                        "chunks": [
                            {
                                "char_count": sum(
                                    len(str(block.get("text", ""))) for block in chunk
                                ),
                                **response,
                            }
                            for chunk, response in zip(
                                chunks, classify_responses, strict=False
                            )
                        ],
                    },
                    None,
                )
            if chunk_index >= len(chunks):
                return None
            return (
                f"pov-classifier:scene:{scene.id}:chunk:{chunk_index}",
                {
                    "mode": "classify",
                    "scene_id": scene.id,
                    "blocks": cast(JsonValue, chunks[chunk_index]),
                    "people": cast(JsonValue, people),
                },
                None,
            )
        if stage == "speaker_attribution":
            selected = [block for block in blocks if block.block_type == "dialogue"]
            if subject_index >= len(selected):
                return None
            block = selected[subject_index]
            previous, subject, following = self._context(block_json, block.id, 4, 4)
            return (
                f"speaker-attribution:block:{block.id}",
                {
                    "previous_blocks": cast(JsonValue, previous),
                    "subject_block": cast(JsonValue, subject),
                    "next_blocks": cast(JsonValue, following),
                    "people": cast(
                        JsonValue,
                        self._people_for_scene(
                            request.document_id,
                            self._dependency_run_id(state, "entity-resolver"),
                            block.scene_id,
                        ),
                    ),
                },
                None,
            )
        if stage == "block_semantics":
            selected = [block for block in blocks if block.block_type == "narration"]
            if subject_index >= len(selected):
                return None
            block = selected[subject_index]
            return (
                f"block-semantic-classifier:block:{block.id}",
                {
                    "block_id": block.id,
                    "text": revision.canonical_text[block.start_cp : block.end_cp],
                },
                None,
            )
        if stage == "entity_resolver":
            mentions = self.entities.repository.list_mentions(
                analysis_run_id=self._dependency_run_id(
                    state, "entity-mention-extractor"
                )
            )
            if subject_index >= len(mentions):
                return None
            mention = mentions[subject_index]
            exact = self.entities.exact_matches(
                document_id=request.document_id, surface=mention.surface
            )
            if len(exact) == 1:
                state["deterministic_subject"] = {
                    "stage": stage,
                    "action": "exact",
                    "mention_id": mention.id,
                    "entity_id": exact[0].id,
                    "scene_id": mention.scene_id,
                }
                return None
            if len(exact) > 1:
                state["deterministic_subject"] = {"stage": stage, "action": "skip"}
                return None
            previous, subject, following = self._context(
                block_json, mention.block_id, 2, 2
            )
            same_scene_ids = set(
                cast(
                    dict[str, list[int]], state.get("entity_resolved_by_scene", {})
                ).get(str(mention.scene_id), [])
            )
            candidates = self.entities.candidate_rows(
                document_id=request.document_id,
                entity_type=mention.entity_type_candidate,
                surface=mention.surface,
                same_scene_ids=same_scene_ids,
            )
            candidates = build_identity_shortlist(
                surface=mention.surface,
                canonical_name=mention.canonical_name_candidate,
                candidate_type=mention.entity_type_candidate,
                identities=candidates,
                same_scene_ids=same_scene_ids,
            )
            if mention.mention_type in {"pronoun", "role_title"}:
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.get("same_scene") is True
                ]
            return (
                f"entity-resolver:mention:{mention.id}",
                {
                    "mention": cast(
                        JsonValue,
                        {
                            "mention_id": mention.id,
                            "surface": mention.surface,
                            "mention_type": mention.mention_type,
                            "entity_type_candidate": mention.entity_type_candidate,
                            "canonical_name_candidate": (
                                mention.canonical_name_candidate
                            ),
                        },
                    ),
                    "previous_blocks": cast(JsonValue, previous),
                    "subject_block": cast(JsonValue, subject),
                    "next_blocks": cast(JsonValue, following),
                    "candidates": cast(JsonValue, candidates),
                },
                None,
            )
        if stage == "term_resolver":
            annotation = self._current_term_candidate_annotation(state)
            if annotation is None:
                return None
            value = self._annotation_value(annotation.value_json)
            term_exact = self.terms.exact_matches(
                document_id=request.document_id, surface=str(value["surface"])
            )
            if len(term_exact) == 1:
                _previous, subject, _following = self._context(
                    block_json, annotation.subject_id, 2, 2
                )
                scene_id = cast(int, subject["scene_id"])
                state["deterministic_subject"] = {
                    "stage": stage,
                    "action": "exact",
                    "term_id": term_exact[0].id,
                    "scene_id": scene_id,
                    "block_id": annotation.subject_id,
                    "start_cp": annotation.start_cp or 0,
                    "end_cp": annotation.end_cp or 0,
                    "surface": str(value["surface"]),
                    "novelty": str(value.get("novelty_candidate", "uncertain")),
                }
                return None
            if len(term_exact) > 1:
                state["deterministic_subject"] = {"stage": stage, "action": "skip"}
                return None
            previous, subject, following = self._context(
                block_json, annotation.subject_id, 2, 2
            )
            scene_id = cast(int, subject["scene_id"])
            same_scene_ids = set(
                cast(dict[str, list[int]], state.get("term_resolved_by_scene", {})).get(
                    str(scene_id), []
                )
            )
            candidates = self.terms.candidate_rows(
                document_id=request.document_id,
                term_type=str(value.get("term_type_candidate", "other")),
                same_scene_ids=same_scene_ids,
            )
            candidates = build_identity_shortlist(
                surface=str(value.get("surface", "")),
                canonical_name=str(value.get("canonical_label_candidate", "")),
                candidate_type=str(value.get("term_type_candidate", "other")),
                identities=candidates,
                same_scene_ids=same_scene_ids,
                id_key="term_id",
                type_key="term_type",
                name_key="canonical_label",
            )
            candidate = {
                "surface": value["surface"],
                "canonical_label_candidate": value["canonical_label_candidate"],
                "term_type_candidate": value["term_type_candidate"],
            }
            return (
                f"term-resolver:candidate:{annotation.id}",
                {
                    "candidate": cast(JsonValue, candidate),
                    "previous_blocks": cast(JsonValue, previous),
                    "subject_block": cast(JsonValue, subject),
                    "next_blocks": cast(JsonValue, following),
                    "candidates": cast(JsonValue, candidates),
                },
                None,
            )
        if stage == "term_explanation":
            term_mentions = self.terms.repository.list_mentions(
                analysis_run_id=self._dependency_run_id(state, "term-resolver")
            )
            if subject_index >= len(term_mentions):
                return None
            term_mention = term_mentions[subject_index]
            term = self.terms.repository.get(term_mention.term_id)
            scene_blocks = [
                item
                for item in block_json
                if item.get("scene_id") == term_mention.scene_id
            ]
            position = next(
                (
                    i
                    for i, item in enumerate(scene_blocks)
                    if item.get("block_id") == term_mention.block_id
                ),
                0,
            )
            start = max(0, position - 2)
            window_end = min(len(scene_blocks), position + 7)
            if str(state.get("stage_substage", "primary")) == "fallback":
                window = scene_blocks[start:]
            else:
                window = scene_blocks[start:window_end]
            block = next(item for item in blocks if item.id == term_mention.block_id)
            substage = str(state.get("stage_substage", "primary"))
            state["term_explanation_has_candidates"] = None
            state["stage_fallback_available"] = window_end < len(scene_blocks)
            return (
                f"term-explanation-detector:term-mention:{term_mention.id}:{substage}",
                {
                    "term_mention_id": term_mention.id,
                    "term_label": term.canonical_label,
                    "mention_block_id": term_mention.block_id,
                    "mention_start_in_block": term_mention.start_cp - block.start_cp,
                    "mention_end_in_block": term_mention.end_cp - block.start_cp,
                    "blocks": cast(JsonValue, window),
                },
                None,
            )
        return None
