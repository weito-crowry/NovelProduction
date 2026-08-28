from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from novel_api.app import create_app
from novel_api.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ApiSettings,
    resolve_data_root,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="novel-api")
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--dev-cors-origin", default=None)
    parser.add_argument("--webui-dist", type=Path, default=None)
    return parser


def _resolve_host(explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    env_host = os.getenv("NOVEL_API_HOST")
    if env_host:
        return env_host
    return DEFAULT_HOST


def _resolve_port(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    env_port = os.getenv("NOVEL_API_PORT")
    if env_port:
        return int(env_port)
    return DEFAULT_PORT


def _resolve_dev_cors_origin(explicit: str | None) -> str | None:
    if explicit is not None:
        return explicit
    env_origin = os.getenv("NOVEL_DEV_CORS_ORIGIN")
    if env_origin:
        return env_origin
    return None


def _resolve_webui_dist(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    env_webui_dist = os.getenv("NOVEL_WEBUI_DIST")
    if env_webui_dist:
        return Path(env_webui_dist)
    return None


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = ApiSettings(
        data_root=resolve_data_root(args.data_root),
        host=_resolve_host(args.host),
        port=_resolve_port(args.port),
        dev_cors_origin=_resolve_dev_cors_origin(args.dev_cors_origin),
        webui_dist=_resolve_webui_dist(args.webui_dist),
    )
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
