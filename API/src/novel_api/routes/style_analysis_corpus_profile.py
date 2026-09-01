from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, Response
from novel_core.style_analysis.fingerprints import JsonObject
from novel_core.style_analysis.profile_service import ProfileBuildResult
from novel_core.style_analysis.runtime_models import JobRecord

from novel_api.dependencies import resolve_project_target
from novel_api.routes._phase1 import envelope
from novel_api.schemas.common import ProjectEnvelope
from novel_api.schemas.style_analysis import (
    AggregateRecomputeRequest,
    CorpusCreateRequest,
    CorpusEpisodeRequest,
    CorpusUpdateRequest,
    CorpusWorkRequest,
    ProfileActivateRequest,
    ProfileFromCorpusRequest,
    ProfileManualRequest,
    ProfileNewVersionRequest,
    ProfilePatchRequest,
    StyleJobResponse,
)
from novel_api.service_container import (
    open_project_read_services,
    open_project_services,
)
from novel_api.style_analysis.job_service import StyleJobService

router = APIRouter()


@router.get("/corpora")
def list_corpora(request: Request, project_id: str) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        corpora = services.style_analysis.list_corpora()
    return envelope(project_id, list(corpora))


@router.post("/corpora", status_code=201)
def create_corpus(
    request: Request, project_id: str, payload: CorpusCreateRequest
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        corpus = services.style_analysis.create_corpus(
            payload.name, payload.description
        )
    return envelope(project_id, corpus)


@router.get("/corpora/compare")
def compare_corpora(
    request: Request,
    project_id: str,
    corpus_id: list[int] = Query(..., min_length=2, max_length=5),  # noqa: B008
) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        result = [
            {
                "corpus_id": item,
                "aggregates": services.style_analysis.list_aggregates(
                    container_type="corpus", container_id=item
                ),
            }
            for item in corpus_id
        ]
    return envelope(project_id, result)


@router.get("/corpora/{corpus_id}")
def get_corpus(
    request: Request, project_id: str, corpus_id: int
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        corpus = services.style_analysis.get_corpus(corpus_id)
        if corpus is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        effective_episode_ids = services.style_analysis.list_effective_corpus_episodes(
            corpus_id
        )
        data = {
            "corpus": corpus,
            "work_memberships": services.style_analysis.list_corpus_work_memberships(
                corpus_id
            ),
            "effective_episode_ids": effective_episode_ids,
        }
    return envelope(project_id, data)


@router.patch("/corpora/{corpus_id}")
def update_corpus(
    request: Request,
    project_id: str,
    corpus_id: int,
    payload: CorpusUpdateRequest,
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.update_corpus(
            corpus_id, name=payload.name, description=payload.description
        )
    return envelope(project_id, result)


@router.delete("/corpora/{corpus_id}", status_code=204)
def delete_corpus(request: Request, project_id: str, corpus_id: int) -> Response:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if not services.style_analysis.delete_corpus(corpus_id):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
    return Response(status_code=204)


@router.post("/corpora/{corpus_id}/works", status_code=201)
def add_corpus_work(
    request: Request,
    project_id: str,
    corpus_id: int,
    payload: CorpusWorkRequest,
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.add_corpus_work(
            corpus_id,
            payload.reference_work_id,
            include_all_episodes=payload.include_all_episodes,
        )
    return envelope(project_id, result)


@router.delete("/corpora/{corpus_id}/works/{work_id}", status_code=204)
def remove_corpus_work(
    request: Request, project_id: str, corpus_id: int, work_id: int
) -> Response:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if not services.style_analysis.remove_corpus_work(corpus_id, work_id):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
    return Response(status_code=204)


@router.put("/corpora/{corpus_id}/episodes/{episode_id}")
def set_corpus_episode(
    request: Request,
    project_id: str,
    corpus_id: int,
    episode_id: int,
    payload: CorpusEpisodeRequest,
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.set_corpus_episode(
            corpus_id, episode_id, payload.mode
        )
    return envelope(project_id, result)


@router.delete("/corpora/{corpus_id}/episodes/{episode_id}", status_code=204)
def remove_corpus_episode(
    request: Request, project_id: str, corpus_id: int, episode_id: int
) -> Response:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        if not services.style_analysis.remove_corpus_episode(corpus_id, episode_id):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
    return Response(status_code=204)


@router.post("/corpora/{corpus_id}/aggregates/recompute", status_code=202)
def recompute_corpus_aggregates(
    request: Request,
    project_id: str,
    corpus_id: int,
    payload: AggregateRecomputeRequest,
) -> ProjectEnvelope[StyleJobResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target):
        pass
    return _enqueue_aggregate_job(
        request,
        project_id,
        container_type="corpus",
        container_id=corpus_id,
        payload=payload,
    )


@router.get("/corpora/{corpus_id}/aggregates")
def list_corpus_aggregates(
    request: Request, project_id: str, corpus_id: int
) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        aggregates = services.style_analysis.list_aggregates(
            container_type="corpus", container_id=corpus_id
        )
    return envelope(project_id, list(aggregates))


@router.post("/reference-works/{work_id}/aggregates/recompute", status_code=202)
def recompute_work_aggregates(
    request: Request,
    project_id: str,
    work_id: int,
    payload: AggregateRecomputeRequest,
) -> ProjectEnvelope[StyleJobResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target):
        pass
    return _enqueue_aggregate_job(
        request,
        project_id,
        container_type="reference_work",
        container_id=work_id,
        payload=payload,
    )


@router.get("/reference-works/{work_id}/aggregates")
def list_work_aggregates(
    request: Request, project_id: str, work_id: int
) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        aggregates = services.style_analysis.list_aggregates(
            container_type="reference_work", container_id=work_id
        )
    return envelope(project_id, list(aggregates))


@router.get("/profiles")
def list_profiles(request: Request, project_id: str) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        profiles = services.style_analysis.list_profiles()
    return envelope(project_id, list(profiles))


@router.post("/profiles/from-corpus", status_code=201)
def create_profile_from_corpus(
    request: Request, project_id: str, payload: ProfileFromCorpusRequest
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.create_profile_from_corpus(
            corpus_id=payload.corpus_id,
            name=payload.name,
            description=payload.description,
            rules=[item.model_dump() for item in payload.rules],
        )
    return envelope(project_id, _profile_build_response(result))


@router.post("/profiles/manual", status_code=201)
def create_manual_profile(
    request: Request, project_id: str, payload: ProfileManualRequest
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.create_manual_profile(
            name=payload.name,
            description=payload.description,
            rules=[item.model_dump() for item in payload.rules],
        )
    return envelope(project_id, _profile_build_response(result))


@router.get("/profiles/{profile_id}")
def get_profile(
    request: Request, project_id: str, profile_id: int
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        profile = services.style_analysis.get_profile(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        versions = services.style_analysis.list_profile_versions(profile_id)
        data = {
            "profile": profile,
            "versions": [
                {
                    "version": version,
                    "rules": services.style_analysis.list_profile_rules(version.id),
                }
                for version in versions
            ],
        }
    return envelope(project_id, data)


@router.patch("/profiles/{profile_id}")
def update_profile(
    request: Request,
    project_id: str,
    profile_id: int,
    payload: ProfilePatchRequest,
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.update_profile(
            profile_id, name=payload.name, description=payload.description
        )
    return envelope(project_id, result)


@router.get("/profiles/{profile_id}/versions")
def list_profile_versions(
    request: Request, project_id: str, profile_id: int
) -> ProjectEnvelope[list[object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        versions = services.style_analysis.list_profile_versions(profile_id)
    return envelope(project_id, list(versions))


@router.get("/profiles/{profile_id}/versions/{version_no}")
def get_profile_version(
    request: Request, project_id: str, profile_id: int, version_no: int
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        version = services.style_analysis.get_profile_version(profile_id, version_no)
        if version is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        rules = services.style_analysis.list_profile_rules(version.id)
    return envelope(project_id, {"version": version, "rules": rules})


@router.post("/profiles/{profile_id}/versions", status_code=201)
def create_profile_version(
    request: Request,
    project_id: str,
    profile_id: int,
    payload: ProfileNewVersionRequest,
) -> ProjectEnvelope[dict[str, object]]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.create_profile_version(
            profile_id,
            parent_version_no=payload.parent_version_no,
            rules=[item.model_dump() for item in payload.rules],
        )
    return envelope(project_id, _profile_build_response(result))


@router.post("/profiles/{profile_id}/activate")
def activate_profile(
    request: Request,
    project_id: str,
    profile_id: int,
    payload: ProfileActivateRequest,
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.activate_profile(
            profile_id, payload.version_no
        )
    return envelope(project_id, result)


@router.post("/profiles/{profile_id}/archive")
def archive_profile(
    request: Request, project_id: str, profile_id: int
) -> ProjectEnvelope[object]:
    target = resolve_project_target(request, project_id)
    with open_project_services(target) as services:
        result = services.style_analysis.archive_profile(profile_id)
    return envelope(project_id, result)


def _enqueue_aggregate_job(
    request: Request,
    project_id: str,
    *,
    container_type: str,
    container_id: int,
    payload: AggregateRecomputeRequest,
) -> ProjectEnvelope[StyleJobResponse]:
    target = resolve_project_target(request, project_id)
    with open_project_read_services(target) as services:
        if container_type == "corpus":
            exists = services.style_analysis.get_corpus(container_id) is not None
        else:
            exists = (
                services.style_analysis.get_reference_work(container_id) is not None
            )
    if not exists:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    service = StyleJobService(
        data_root=request.app.state.settings.data_root,
        notify=request.app.state.style_analysis_worker.notify,
    )
    job_payload = cast(
        JsonObject,
        {
            "container_type": container_type,
            "container_id": container_id,
            "measurement_target_type": payload.measurement_target_type,
            "filter": payload.filter,
            "metric_names": payload.metric_names,
        },
    )
    job = service.enqueue(
        project_id,
        "recompute_aggregate",
        job_payload,
    )
    return envelope(project_id, _job_response(job))


def _job_response(job: JobRecord) -> StyleJobResponse:
    result = json.loads(job.result_json)
    warnings = json.loads(job.warning_json)
    return StyleJobResponse(
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress={"current": job.progress_current, "total": job.progress_total},
        result=result if isinstance(result, dict) else {},
        warnings=warnings if isinstance(warnings, list) else [],
        error_code=job.error_code,
        error_message=job.error_message,
    )


def _profile_build_response(result: ProfileBuildResult) -> dict[str, object]:
    return {
        "profile": result.profile,
        "version": result.version,
        "rules": list(result.rules),
        "warnings": list(result.warnings),
    }
