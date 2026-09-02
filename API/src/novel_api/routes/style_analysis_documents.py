from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.style_analysis import (
    StyleStructureMergeRequest,
    StyleStructureSplitRequest,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)

router = APIRouter()


@router.get("/documents")
def list_style_documents(
    request: Request, project_id: str
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        documents = services.style_analysis.list_documents()
    return envelope(project_id, list(documents))


@router.get("/documents/{document_id}")
def get_style_document(
    request: Request, project_id: str, document_id: int
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        document = services.style_analysis.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return envelope(project_id, document)


@router.get("/documents/{document_id}/revisions")
def list_style_text_revisions(
    request: Request, project_id: str, document_id: int
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_document(document_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        revisions = services.style_analysis.list_text_revisions(document_id)
    return envelope(project_id, list(revisions))


@router.get("/documents/{document_id}/text")
def get_style_text(
    request: Request,
    project_id: str,
    document_id: int,
    text_revision_id: int = Query(..., gt=0),
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_document(document_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        text = services.style_analysis.get_text(document_id, text_revision_id)
    return envelope(project_id, text)


@router.get("/documents/{document_id}/structures")
def list_style_structures(
    request: Request, project_id: str, document_id: int
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_document(document_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        structures = services.style_analysis.list_structure_revisions(document_id)
    return envelope(project_id, list(structures))


@router.get("/documents/{document_id}/structure")
def get_style_structure(
    request: Request,
    project_id: str,
    document_id: int,
    structure_revision_id: int = Query(..., gt=0),
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if services.style_analysis.get_document(document_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        structure = services.style_analysis.get_structure(
            document_id, structure_revision_id
        )
    return envelope(project_id, structure)


@router.post(
    "/documents/{document_id}/structures/{structure_revision_id}/select-current"
)
def select_current_style_structure(
    request: Request,
    project_id: str,
    document_id: int,
    structure_revision_id: int,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if services.style_analysis.get_document(document_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        document = services.style_analysis.select_current_structure(
            document_id, structure_revision_id
        )
    return envelope(project_id, document)


@router.post("/documents/{document_id}/scenes/{scene_id}/split")
def split_style_scene(
    request: Request,
    project_id: str,
    document_id: int,
    scene_id: int,
    payload: StyleStructureSplitRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if services.style_analysis.get_document(document_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        structure = services.style_analysis.split_structure_scene(
            document_id=document_id,
            scene_id=scene_id,
            after_block_id=payload.after_block_id,
            expected_structure_revision_id=payload.expected_structure_revision_id,
        )
    return envelope(project_id, structure)


@router.post("/documents/{document_id}/scenes/merge")
def merge_style_scenes(
    request: Request,
    project_id: str,
    document_id: int,
    payload: StyleStructureMergeRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if services.style_analysis.get_document(document_id) is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        structure = services.style_analysis.merge_structure_scenes(
            document_id=document_id,
            scene_id=payload.scene_id,
            next_scene_id=payload.next_scene_id,
            expected_structure_revision_id=payload.expected_structure_revision_id,
        )
    return envelope(project_id, structure)


@router.get("/documents/{document_id}/runs")
def list_analysis_runs(
    request: Request, project_id: str, document_id: int
) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(
            project_id, list(services.style_analysis.list_analysis_runs(document_id))
        )


@router.get("/documents/{document_id}/semantics")
def get_document_semantics(
    request: Request,
    project_id: str,
    document_id: int,
    structure_revision_id: int = Query(..., gt=0),
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        semantics = services.style_analysis.get_semantics(
            document_id, structure_revision_id
        )
    return envelope(project_id, semantics)


@router.get("/documents/{document_id}/metrics")
def get_document_metrics(
    request: Request,
    project_id: str,
    document_id: int,
    structure_revision_id: int = Query(..., gt=0),
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        metrics = services.style_analysis.list_metrics(
            document_id, structure_revision_id
        )
    return envelope(project_id, metrics)


@router.get("/documents/{document_id}/scenes/{scene_id}/metrics")
def get_scene_metrics(
    request: Request,
    project_id: str,
    document_id: int,
    scene_id: int,
    structure_revision_id: int = Query(..., gt=0),
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        metrics = services.style_analysis.list_metrics(
            document_id, structure_revision_id, scene_id
        )
    return envelope(project_id, metrics)


@router.get("/documents/{document_id}/annotations")
def list_analysis_annotations(
    request: Request, project_id: str, document_id: int
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(
            project_id, list(services.style_analysis.list_annotations(document_id))
        )


@router.get("/documents/{document_id}/boundary-proposals")
def list_boundary_proposals(
    request: Request,
    project_id: str,
    document_id: int,
    min_confidence: float = Query(0.60, ge=0.0, le=1.0),
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        return envelope(
            project_id,
            list(
                services.style_analysis.list_boundary_proposals(
                    document_id, min_confidence=min_confidence
                )
            ),
        )


@router.get("/documents/{document_id}/structure/boundary-proposals")
def list_structure_boundary_proposals(
    request: Request,
    project_id: str,
    document_id: int,
    include_below_threshold: bool = Query(False),
) -> ProjectEnvelope[list[dict[str, object]]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        proposals = services.style_analysis.list_boundary_proposals(
            document_id,
            include_below_threshold=include_below_threshold,
        )
    return envelope(project_id, list(proposals))
