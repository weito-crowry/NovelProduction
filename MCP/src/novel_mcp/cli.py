from __future__ import annotations

import argparse
from pathlib import Path

from novel_core.initialization import initialize_work
from novel_core.services.work_service import PRODUCTION_STATUSES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--working-title", "--title", dest="working_title", required=True
    )
    parser.add_argument("--genre", default="")
    parser.add_argument("--premise", default="")
    parser.add_argument("--themes-json", default="{}")
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--production-status", choices=sorted(PRODUCTION_STATUSES), default="planned"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    initialize_work(
        args.db,
        working_title=args.working_title,
        genre=args.genre,
        premise=args.premise,
        themes_json=args.themes_json,
        description=args.description,
        production_status=args.production_status,
    )
    return 0
