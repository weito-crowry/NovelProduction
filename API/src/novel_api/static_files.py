from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response


def validate_webui_dist(webui_dist: Path) -> Path:
    resolved_dist = webui_dist.resolve()
    if not resolved_dist.exists():
        raise ValueError(f"webui_dist does not exist: {webui_dist}")
    if not resolved_dist.is_dir():
        raise ValueError(f"webui_dist must be a directory: {webui_dist}")

    index_path = resolved_dist / "index.html"
    if not index_path.is_file():
        raise ValueError(f"webui_dist must contain index.html: {webui_dist}")
    try:
        index_path.resolve().relative_to(resolved_dist)
    except ValueError as exc:
        raise ValueError(f"webui_dist must contain index.html: {webui_dist}") from exc
    return resolved_dist


def install_webui_routes(app: FastAPI, webui_dist: Path) -> None:
    resolved_dist = validate_webui_dist(webui_dist)
    index_path = resolved_dist / "index.html"

    @app.api_route(
        "/{path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    def serve_webui(path: str) -> Response:
        request_path = "/" + path.lstrip("/")
        if request_path == "/api/v1" or request_path.startswith("/api/v1/"):
            raise HTTPException(status_code=404)

        candidate = _resolve_candidate(resolved_dist, path)
        if candidate is None:
            raise HTTPException(status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path)


def _resolve_candidate(dist: Path, raw_path: str) -> Path | None:
    decoded_path = unquote(unquote(raw_path)).replace("\\", "/")
    parts = PurePosixPath(decoded_path.lstrip("/")).parts
    try:
        candidate = dist.joinpath(*parts).resolve()
        candidate.relative_to(dist)
    except (OSError, ValueError):
        return None
    return candidate
