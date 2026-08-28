from __future__ import annotations

from fastapi import HTTPException, Request

from novel_api.project_registry import ProjectNotFoundError, ProjectRegistry
from novel_api.service_container import ProjectDescriptor, ProjectTarget


def resolve_project_target(request: Request, project_id: str) -> ProjectTarget:
    try:
        ProjectRegistry._validate_project_id(project_id)
        project_dir = request.app.state.settings.data_root / project_id
        story_db = project_dir / "story.db"
        if (
            project_dir.is_symlink()
            or not project_dir.is_dir()
            or not story_db.is_file()
        ):
            raise ProjectNotFoundError("PROJECT_NOT_FOUND")
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="PROJECT_NOT_FOUND") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProjectTarget(
        project_id=project_id,
        descriptor=ProjectDescriptor(project_dir=project_dir, story_db=story_db),
    )
