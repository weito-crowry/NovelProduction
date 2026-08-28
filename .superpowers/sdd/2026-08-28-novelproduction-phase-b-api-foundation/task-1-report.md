# Task 1 Report

## Files Changed

- `API/pyproject.toml`
- `API/src/novel_api/__init__.py`
- `API/src/novel_api/app.py`
- `API/src/novel_api/cli.py`
- `API/src/novel_api/config.py`
- `API/src/novel_api/routes/__init__.py`
- `API/src/novel_api/routes/health.py`
- `API/tests/test_health.py`
- `API/tests/test_cli.py`

## RED Evidence

First RED attempt:

- `cd API`
- `uv sync --all-groups`
- `uv run pytest tests/test_health.py tests/test_cli.py -q`

Result:

- `uv sync` failed because `API/src` did not exist yet.

Second RED attempt, after creating only the minimal package scaffold needed for the build:

- `cd API`
- `uv sync --all-groups`
- `uv run pytest tests/test_health.py tests/test_cli.py -q`

Result:

- Test collection failed with the expected missing-implementation errors:
  - `ModuleNotFoundError: No module named 'novel_api.app'`
  - `ModuleNotFoundError: No module named 'novel_api.cli'`

## GREEN Evidence

Focused API tests:

- `uv run pytest tests/test_health.py tests/test_cli.py -q`
- Result: `4 passed in 0.90s`

Package checks:

- `uv run ruff check .`
- Result: `All checks passed!`

- `uv run ruff format --check .`
- Result: `8 files already formatted`

- `uv run mypy src`
- Result: `Success: no issues found in 6 source files`

## Self-Review

- `create_app(settings: ApiSettings)` builds a FastAPI app, registers only the health router, and does not discover projects or open a database.
- `GET /api/v1/health` returns exactly `{"status": "ok", "api_version": "v1"}`.
- `main(argv: list[str] | None = None)` resolves `data_root`, `host`, `port`, and `dev_cors_origin` from CLI args and environment variables, then calls `uvicorn.run(app, host=..., port=...)`.
- The CLI tests cover default host/port behavior, explicit `--host`, `--port`, and `--data-root`, plus `NOVEL_DATA_ROOT`, `NOVEL_API_HOST`, `NOVEL_API_PORT`, and `NOVEL_DEV_CORS_ORIGIN`.

## Concerns

- None for Task 1. The next phase will add project registry and request-scoped database behavior.
