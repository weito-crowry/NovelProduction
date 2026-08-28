from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from novel_api.config import ApiSettings
from novel_api.routes import health_router


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.include_router(health_router)

    if settings.dev_cors_origin is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.dev_cors_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    return app
