from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query, Request, status
from novel_core.document import (
    AnnotationProjection,
    export_document,
    render_web_html,
    serialize_authoring_html,
    serialize_document_json,
)
from novel_core.errors import ValidationError, VersionConflictError

from novel_api.dependencies import resolve_project_target
from novel_api.errors import ApiVersionConflictError, build_conflict_details
from novel_api.routes._phase1 import envelope
from novel_api.schemas.authoring import DraftSave
from novel_api.schemas.common import ProjectEnvelope
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["authoring"])


@router.get(
    "/episodes/{episode_id}/outline",
    response_model=ProjectEnvelope[Any],
)
def get_episode_outline(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.outline.get_episode_outline(episode_id))


@router.get(
    "/episodes/{episode_id}/context",
    response_model=ProjectEnvelope[Any],
)
def get_episode_context(
    request: Request, project_id: str, episode_id: int
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.context.build_episode_context(episode_id))


@router.get(
    "/episodes/{episode_id}/draft",
    response_model=ProjectEnvelope[Any],
)
def get_episode_draft(
    request: Request,
    project_id: str,
    episode_id: int,
    revision: int | None = Query(default=None, ge=1),
    format: str = Query(default="html"),
    annotation_projection: str = Query(default="none"),
    annotation_keys: list[str] | None = Query(default=None),  # noqa: B008
    include_notes: bool = Query(default=False),
) -> ProjectEnvelope[Any]:
    projection = _draft_projection(
        format, annotation_projection, annotation_keys, include_notes
    )
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        draft = services.draft.get_draft(episode_id, revision)
        return envelope(
            project_id,
            None
            if draft is None
            else _draft_read(draft, format, projection, include_notes),
        )


@router.post(
    "/episodes/{episode_id}/drafts",
    response_model=ProjectEnvelope[Any],
    status_code=status.HTTP_201_CREATED,
)
def save_episode_draft(
    request: Request,
    project_id: str,
    episode_id: int,
    body: DraftSave,
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        try:
            saved = services.draft.save_draft(
                episode_id,
                plain_text=body.plain_text,
                html=body.html,
                metadata_updates=_metadata_updates(body),
                restore_revision=body.restore_revision,
                expected_parent_draft_id=body.expected_parent_draft_id,
                source_agent=body.source_agent,
                change_summary=body.change_summary,
            )
        except VersionConflictError:
            latest = services.draft.get_draft(episode_id)
            if latest is None or body.expected_parent_draft_id is None:
                raise
            raise ApiVersionConflictError(
                build_conflict_details(
                    entity_type="draft",
                    entity_id=episode_id,
                    expected_version=body.expected_parent_draft_id,
                    current_version=latest.id,
                    current_resource=_draft_read(
                        latest,
                        "html",
                        AnnotationProjection("selected", ("emotions",)),
                        True,
                    ),
                )
            ) from None
        return envelope(project_id, saved)


@router.get(
    "/episodes/{episode_id}/drafts",
    response_model=ProjectEnvelope[Any],
)
def list_episode_drafts(
    request: Request,
    project_id: str,
    episode_id: int,
    limit: int = Query(default=20, ge=1, le=100),
) -> ProjectEnvelope[Any]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(project_id, services.draft.history(episode_id, limit))


@router.get(
    "/episodes/{episode_id}/draft/export",
    response_model=ProjectEnvelope[Any],
)
def export_episode_draft(
    request: Request,
    project_id: str,
    episode_id: int,
    revision: int | None = Query(default=None, ge=1),
    format: str = Query(default="narou"),
) -> ProjectEnvelope[Any]:
    if format != "narou":
        raise ValidationError("format must be 'narou'", field="format")
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        draft = services.draft.get_draft(episode_id, revision)
        if draft is None:
            return envelope(project_id, None)
        exported = export_document(draft.document, format)
        return envelope(
            project_id,
            {
                "format": exported.format,
                "media_type": exported.media_type,
                "content": exported.content,
                "suggested_filename": f"episode-{episode_id}-r{draft.revision}.txt",
                "warnings": exported.warnings,
            },
        )


def _metadata_updates(body: DraftSave) -> dict[str, dict[str, object]] | None:
    if body.metadata_updates is None:
        return None
    return {
        block_id: patch.model_dump(exclude_unset=True)
        for block_id, patch in body.metadata_updates.items()
    }


def _draft_projection(
    format: str,
    annotation_projection: str,
    annotation_keys: list[str] | None,
    include_notes: bool,
) -> AnnotationProjection:
    keys = tuple(annotation_keys or ())
    if any(not key for key in keys):
        raise ValidationError(
            "annotation_keys must be non-empty", field="annotation_keys"
        )
    if format not in {"html", "web", "document"}:
        raise ValidationError("unsupported draft format", field="format")
    if annotation_projection not in {"none", "selected", "all"}:
        raise ValidationError(
            "unsupported annotation projection", field="annotation_projection"
        )
    if format == "html":
        if include_notes:
            raise ValidationError(
                "include_notes is not relevant for html", field="include_notes"
            )
        if annotation_projection == "none" and keys:
            raise ValidationError("annotation_keys require selected projection")
        if annotation_projection == "selected" and not keys:
            raise ValidationError("selected projection requires annotation_keys")
        if annotation_projection == "all" and keys:
            raise ValidationError("all projection does not accept annotation_keys")
        return AnnotationProjection(annotation_projection, keys)
    if annotation_projection != "none" or keys:
        raise ValidationError(
            "annotation projection is only available for html",
            field="annotation_projection",
        )
    if format == "document" and include_notes:
        raise ValidationError(
            "include_notes is not relevant for document", field="include_notes"
        )
    return AnnotationProjection("none")


def _draft_read(
    draft: Any,
    format: str,
    projection: AnnotationProjection,
    include_notes: bool,
) -> dict[str, Any]:
    if format == "html":
        content: Any = serialize_authoring_html(draft.document, projection)
    elif format == "web":
        content = render_web_html(draft.document, include_notes=include_notes)
    else:
        content = json.loads(serialize_document_json(draft.document))
    return {
        "id": draft.id,
        "work_id": draft.work_id,
        "episode_id": draft.episode_id,
        "revision": draft.revision,
        "parent_draft_id": draft.parent_draft_id,
        "format": format,
        "content": content,
        "source_agent": draft.source_agent,
        "change_summary": draft.change_summary,
        "created_at": draft.created_at,
    }
