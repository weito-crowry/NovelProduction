from __future__ import annotations

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
    relationships_router,
    timeline_router,
    work_router,
    world_router,
)
from novel_api.routes.authoring import router as authoring_router
from novel_api.routes.views import router as views_router


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
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
    app.include_router(views_router)

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
