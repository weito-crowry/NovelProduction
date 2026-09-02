from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from novel_api.config import ApiSettings
from novel_api.errors import install_exception_handlers
from novel_api.routes import (
    canon_router,
    characters_router,
    health_router,
    information_router,
    narrative_router,
    projects_router,
    reader_router,
    relationships_router,
    style_analysis_router,
    timeline_router,
    work_router,
    world_router,
)
from novel_api.routes.authoring import router as authoring_router
from novel_api.routes.views import router as views_router
from novel_api.static_files import install_webui_routes
from novel_api.style_analysis.execution import execute_style_job
from novel_api.style_analysis.job_worker import StyleAnalysisWorker
from novel_api.style_analysis.model_client import build_model_client


def create_app(settings: ApiSettings) -> FastAPI:
    model_client = build_model_client(settings)
    worker = StyleAnalysisWorker(
        data_root=settings.data_root,
        executor=lambda connection, job: execute_style_job(
            connection,
            job,
            model_client=model_client,
            model_provider=settings.style_model_provider
            if model_client is not None
            else None,
            model_id=settings.style_model_id if model_client is not None else None,
        ),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.style_analysis_worker = worker
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(work_router)
    app.include_router(world_router)
    app.include_router(timeline_router)
    app.include_router(characters_router)
    app.include_router(relationships_router)
    app.include_router(canon_router)
    app.include_router(narrative_router)
    app.include_router(information_router)
    app.include_router(authoring_router)
    app.include_router(reader_router)
    app.include_router(style_analysis_router)
    app.include_router(views_router)
    if settings.webui_dist is not None:
        install_webui_routes(app, settings.webui_dist)

    if settings.dev_cors_origin == "*":
        raise ValueError("development CORS origin cannot be a wildcard")
    if settings.dev_cors_origin is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.dev_cors_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    return app
