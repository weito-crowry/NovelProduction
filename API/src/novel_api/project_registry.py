from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from novel_core.config import DatabaseConfig
from novel_core.database import (
    assert_database_integrity,
    default_migration_dir,
    open_database,
)
from novel_core.initialization import initialize_work
from novel_core.services.work_service import WorkService
from pydantic import ValidationError

from novel_api.schemas.projects import (
    MetadataState,
    ProjectHealth,
    ProjectMetadata,
    ProjectStatus,
    ProjectSummary,
    validate_utc_timestamp,
)

_PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$", re.ASCII)
_UTC = timezone(timedelta(0))


def _utc_now() -> datetime:
    return datetime.now(_UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProjectNotFoundError(LookupError):
    """Raised when a valid project ID has no immediate story database."""


class ProjectConflictError(RuntimeError):
    """Raised when project creation cannot claim the requested ID."""


class ProjectRegistry:
    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root

    def list(self, include_archived: bool = False) -> list[ProjectSummary]:
        if not self._data_root.is_dir():
            return []
        projects: list[ProjectSummary] = []
        for project_dir in sorted(
            self._data_root.iterdir(), key=lambda path: path.name
        ):
            if (
                project_dir.is_symlink()
                or not project_dir.is_dir()
                or not self._is_valid_project_id(project_dir.name)
                or not (project_dir / "story.db").is_file()
            ):
                continue
            summary = self._summarize(project_dir)
            if include_archived or summary.status != "archived":
                projects.append(summary)
        return projects

    def get(self, project_id: str) -> ProjectSummary:
        self._validate_project_id(project_id)
        project_dir = self._data_root / project_id
        if (
            project_dir.is_symlink()
            or not project_dir.is_dir()
            or not (project_dir / "story.db").is_file()
        ):
            raise ProjectNotFoundError("PROJECT_NOT_FOUND")
        return self._summarize(project_dir)

    def create(
        self, working_title: str, project_id: str | None = None
    ) -> ProjectSummary:
        if not isinstance(working_title, str) or not working_title.strip():
            raise ValueError("working_title must be non-empty")
        if project_id is not None:
            self._validate_project_id(project_id)

        self._data_root.mkdir(parents=True, exist_ok=True)
        locks_dir = self._data_root / ".locks"
        staging_root = self._data_root / ".staging"
        locks_dir.mkdir(exist_ok=True)
        staging_root.mkdir(exist_ok=True)

        selected_id, lock_path = self._claim_project_id(project_id, locks_dir)
        staging_dir = staging_root / uuid4().hex
        final_dir = self._data_root / selected_id
        try:
            staging_dir.mkdir()
            story_db_path = staging_dir / "story.db"
            initialize_work(story_db_path, working_title=working_title)
            connection = open_database(
                DatabaseConfig(
                    db_path=story_db_path,
                    migration_dir=default_migration_dir(),
                )
            )
            try:
                assert_database_integrity(connection)
            finally:
                connection.close()

            timestamp = _format_timestamp(_utc_now())
            metadata = ProjectMetadata(
                project_id=selected_id,
                status="active",
                created_at=timestamp,
                updated_at=timestamp,
            )
            self._write_metadata(staging_dir / "project.json", metadata)
            if final_dir.exists():
                raise ProjectConflictError("PROJECT_CONFLICT")
            try:
                staging_dir.rename(final_dir)
            except FileExistsError as exc:
                raise ProjectConflictError("PROJECT_CONFLICT") from exc
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise
        finally:
            lock_path.unlink(missing_ok=True)

        return self.get(selected_id)

    def set_status(self, project_id: str, status: ProjectStatus) -> ProjectSummary:
        if status not in ("active", "archived"):
            raise ValueError("invalid project status")
        self.get(project_id)
        now = _format_timestamp(_utc_now())
        prior_created_at = self._read_valid_created_at(
            self._data_root / project_id / "project.json"
        )
        metadata = ProjectMetadata(
            project_id=project_id,
            status=status,
            created_at=prior_created_at or now,
            updated_at=now,
        )
        project_dir = self._data_root / project_id
        metadata_path = project_dir / "project.json"
        temporary_path = project_dir / f".project.json.{uuid4().hex}.tmp"
        try:
            self._write_metadata(temporary_path, metadata)
            os.replace(temporary_path, metadata_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return self.get(project_id)

    def _claim_project_id(
        self, project_id: str | None, locks_dir: Path
    ) -> tuple[str, Path]:
        if project_id is not None:
            self._validate_project_id(project_id)
            return project_id, self._acquire_lock(project_id, locks_dir)

        base = f"project-{_utc_now().strftime('%Y%m%d-%H%M%S')}"
        suffix = 1
        while True:
            candidate = base if suffix == 1 else f"{base}-{suffix}"
            if (self._data_root / candidate).exists():
                suffix += 1
                continue
            try:
                return candidate, self._acquire_lock(candidate, locks_dir)
            except ProjectConflictError:
                suffix += 1

    @staticmethod
    def _acquire_lock(project_id: str, locks_dir: Path) -> Path:
        lock_path = locks_dir / f"{project_id}.lock"
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ProjectConflictError("PROJECT_CONFLICT") from exc
        os.close(descriptor)
        return lock_path

    def _summarize(self, project_dir: Path) -> ProjectSummary:
        metadata, metadata_state = self._read_metadata(project_dir)
        status: ProjectStatus = "active" if metadata is None else metadata.status
        created_at = None if metadata is None else metadata.created_at
        updated_at = None if metadata is None else metadata.updated_at

        working_title: str | None = None
        health: ProjectHealth = "degraded"
        connection: sqlite3.Connection | None = None
        try:
            connection = open_database(
                DatabaseConfig(
                    db_path=project_dir / "story.db",
                    migration_dir=default_migration_dir(),
                )
            )
            working_title = WorkService(connection).get().working_title
            health = "ok"
        except Exception:
            working_title = None
        finally:
            if connection is not None:
                connection.close()

        return ProjectSummary(
            project_id=project_dir.name,
            status=status,
            metadata_state=metadata_state,
            working_title=working_title,
            created_at=created_at,
            updated_at=updated_at,
            health=health,
        )

    @staticmethod
    def _write_metadata(path: Path, metadata: ProjectMetadata) -> None:
        path.write_text(
            json.dumps(metadata.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read_metadata(
        self, project_dir: Path
    ) -> tuple[ProjectMetadata | None, MetadataState]:
        metadata_path = project_dir / "project.json"
        if not metadata_path.exists():
            return None, "missing"
        try:
            metadata = ProjectMetadata.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValidationError):
            return None, "invalid"
        if metadata.project_id != project_dir.name or not self._is_valid_project_id(
            metadata.project_id
        ):
            return None, "invalid"
        return metadata, "ok"

    @staticmethod
    def _read_valid_created_at(metadata_path: Path) -> str | None:
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            created_at = raw.get("created_at") if isinstance(raw, dict) else None
            if not isinstance(created_at, str):
                return None
            validate_utc_timestamp(created_at)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return None
        return created_at

    @staticmethod
    def _is_valid_project_id(project_id: str) -> bool:
        return _PROJECT_ID_PATTERN.fullmatch(project_id) is not None

    @classmethod
    def _validate_project_id(cls, project_id: str) -> None:
        if not isinstance(project_id, str) or not cls._is_valid_project_id(project_id):
            raise ValueError("invalid project_id")
