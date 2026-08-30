from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

MIGRATION_NAMES = (
    "001_initial.sql",
    "002_search.sql",
    "003_narrative.sql",
    "004_drafts.sql",
)


def _venv_python(venv_dir: Path) -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    return venv_dir / scripts_dir / executable


def _clean_subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for variable in (
        "PYTHONHOME",
        "PYTHONPATH",
        "UV_INTERNAL__PYTHONHOME",
        "UV_PROJECT_ENVIRONMENT",
        "VIRTUAL_ENV",
    ):
        environment.pop(variable, None)
    return environment


def test_installed_wheel_contains_and_uses_core_migrations(tmp_path: Path) -> None:
    core_root = Path(__file__).resolve().parents[1]
    build_root = tmp_path / "core-source"
    shutil.copytree(
        core_root,
        build_root,
        ignore=shutil.ignore_patterns(
            ".venv",
            "build",
            "*.egg-info",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".coverage",
        ),
    )
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    environment = _clean_subprocess_environment()
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheel_dir)],
        cwd=build_root,
        env=environment,
        check=True,
    )
    wheel_paths = tuple(wheel_dir.glob("*.whl"))
    assert len(wheel_paths) == 1
    with zipfile.ZipFile(wheel_paths[0]) as archive:
        migration_paths = tuple(
            path
            for path in sorted(archive.namelist())
            if path.startswith("novel_core/migrations/")
        )
    assert migration_paths == tuple(
        f"novel_core/migrations/{name}" for name in MIGRATION_NAMES
    )

    venv_dir = tmp_path / "venv"
    subprocess.run(["uv", "venv", str(venv_dir)], env=environment, check=True)
    python = _venv_python(venv_dir)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel_paths[0])],
        cwd=tmp_path,
        env=environment,
        check=True,
    )

    smoke = f"""
import sqlite3
import sys
from pathlib import Path

import novel_core
from novel_core.document import is_formal_block_id, new_block_id
from novel_core.database import default_migration_dir
from novel_core.initialization import initialize_work

db_path = Path(sys.argv[1])
generated_block_id = new_block_id()
assert is_formal_block_id(generated_block_id)
migration_dir = default_migration_dir()
assert migration_dir.is_dir()
assert migration_dir == Path(novel_core.__file__).resolve().parent / 'migrations'
assert tuple(
    path.name for path in sorted(migration_dir.glob('*.sql'))
) == {MIGRATION_NAMES!r}
initialize_work(db_path, 'wheel install smoke')
with sqlite3.connect(db_path) as connection:
    assert connection.execute(
        'SELECT version FROM schema_migrations ORDER BY version'
    ).fetchall() == [
        ('001_initial.sql',),
        ('002_search.sql',),
        ('003_narrative.sql',),
        ('004_drafts.sql',),
    ]
    assert connection.execute(
        'SELECT slug, working_title FROM works'
    ).fetchone() == ('main', 'wheel install smoke')
    """
    db_path = tmp_path / "installed-wheel.db"
    subprocess.run(
        [str(python), "-c", smoke, str(db_path)],
        cwd=tmp_path,
        env=environment,
        check=True,
    )
