from novel_api.routes.canon import router as canon_router
from novel_api.routes.characters import (
    characters_router,
    relationships_router,
)
from novel_api.routes.health import router as health_router
from novel_api.routes.information import router as information_router
from novel_api.routes.narrative import router as narrative_router
from novel_api.routes.projects import router as projects_router
from novel_api.routes.reader import router as reader_router
from novel_api.routes.style_analysis import router as style_analysis_router
from novel_api.routes.timeline import router as timeline_router
from novel_api.routes.work import router as work_router
from novel_api.routes.world import router as world_router

__all__ = [
    "canon_router",
    "characters_router",
    "health_router",
    "information_router",
    "narrative_router",
    "projects_router",
    "reader_router",
    "style_analysis_router",
    "relationships_router",
    "timeline_router",
    "work_router",
    "world_router",
]
