from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from setuptools import build_meta as _original_backend
from setuptools.build_meta import *  # noqa: F403


@contextmanager
def _stage_migrations() -> Iterator[None]:
    project_root = Path(__file__).resolve().parents[1]
    source_dir = project_root / "migrations"
    package_dir = project_root / "src" / "novel_core" / "migrations"
    migration_paths = tuple(sorted(source_dir.glob("*.sql")))
    if not migration_paths:
        raise RuntimeError(f"No migrations found in {source_dir}")
    if package_dir.exists():
        raise RuntimeError(f"Refusing to overwrite {package_dir}")

    package_dir.mkdir()
    try:
        for migration_path in migration_paths:
            shutil.copyfile(migration_path, package_dir / migration_path.name)
        yield
    finally:
        shutil.rmtree(package_dir)


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, object] | None = None,
    metadata_directory: str | None = None,
) -> str:
    with _stage_migrations():
        return _original_backend.build_wheel(
            wheel_directory, config_settings, metadata_directory
        )
