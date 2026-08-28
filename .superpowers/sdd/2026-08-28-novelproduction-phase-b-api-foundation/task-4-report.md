# Task 4 Report: Shared API error contract

## Status

COMPLETE

## Scope implemented

- Added the generic `ProjectEnvelope[T]` success envelope and shared error models.
- Added recursive serialization for Pydantic models, dataclasses, mappings, tuples,
  lists, and JSON scalar values.
- Serialization rejects raw exceptions, SQLite connections, and unsupported objects
  instead of passing them to response encoding.
- Added one `install_exception_handlers()` entry point and called it from
  `create_app()`.
- Normalized every required FastAPI, CORE, project-registry, and SQLite exception for
  `/api/v1` while keeping non-API failures on a plain FastAPI-style 500 response.
- Added sanitized messages, request-path `project_id` extraction, and
  `details.domain_code` for normalized CORE domain errors.
- Added `build_conflict_details()` with explicit expected/current versions and either
  a caller-supplied current resource or a caller-supplied safe-read callback. The
  helper has no database configuration, connection creation, exception-string
  parsing, or independent lookup behavior.
- Preserved the health response and adapted existing project-route expectations to
  the shared error envelope without changing registry semantics.

## Error mappings verified

| Source exception | HTTP | API code |
| --- | ---: | --- |
| `RequestValidationError`, CORE `ValidationError`, `ValueError` | 400 | `VALIDATION_ERROR` |
| `ProjectNotFoundError` | 404 | `PROJECT_NOT_FOUND` |
| Every current CORE `*NotFoundError`, `WorkScopeError` | 404 | `NOT_FOUND` |
| `VersionConflictError` | 409 | `VERSION_CONFLICT` |
| `OrderConflictError` | 409 | `ORDER_CONFLICT` |
| `RelationshipIntegrityError`, `sqlite3.IntegrityError` | 409 | `DEPENDENCY_CONFLICT` |
| `CanonPolicyError` | 409 | `DEPENDENCY_CONFLICT` |
| locked/busy `sqlite3.OperationalError` | 503 | `DATABASE_BUSY` |
| non-locking SQLite operational and unexpected exceptions | 500 | `INTERNAL_ERROR` |

The existing Task 2 `PROJECT_CONFLICT` response is also preserved as a structured
409 response.

## TDD evidence

### Initial RED: interface absent

Command:

```text
cd API
uv run pytest -W error tests/test_errors.py -q
```

Result: collection failed as expected because `novel_api.errors` did not exist:

```text
E   ModuleNotFoundError: No module named 'novel_api.errors'
1 error in 0.35s
```

This collection result was not accepted as sufficient behavior evidence.

### Behavior-level RED: non-working public stubs

After adding only importable public stubs, the same command exercised the real app
and failed on observable behavior:

```text
FFFFFFFFFFFFFFFFFFFFF..FFFFFF
27 failed, 2 passed in 1.08s
```

Representative failures were:

- CORE validation returned 500 instead of the required 400.
- FastAPI request validation returned 422 instead of 400.
- API exceptions returned plain `Internal Server Error` instead of JSON.
- `ProjectEnvelope` could not receive a serialized dataclass because the serializer
  returned the dataclass unchanged.
- SQLite connections and raw exceptions were not rejected.
- Conflict details returned `{}` and did not invoke the supplied safe callback.
- Global version-conflict fallback returned 500 instead of 409.

### GREEN

Command:

```text
uv run pytest -W error tests/test_errors.py -q
```

Result:

```text
.............................
29 passed in 0.60s
```

The focused suite covers every required mapping, every current CORE not-found type,
validation shape, project-ID extraction, domain codes, sanitization, API-only JSON
fallback, unchanged health, project envelope/serialization, explicit conflict
snapshots, callback snapshots, and version-conflict fallback without parsed details.

## Verification evidence

All commands were run from the isolated Task 4 worktree on 2026-08-28.

### API dependency sync

```text
uv sync --all-groups
Resolved 48 packages in 2ms
Checked 47 packages in 5ms
```

No dependency or lockfile changes resulted.

### Focused API suite

```text
uv run pytest -W error tests/test_errors.py -q
29 passed in 0.60s
```

### Full API suite

```text
uv run pytest -W error -q
64 passed in 2.94s
```

### Full CORE suite

```text
uv run pytest -W error -q
138 passed in 10.51s
```

### API quality gates

```text
uv run ruff check .
All checks passed!

uv run ruff format --check .
22 files already formatted

uv run mypy src
Success: no issues found in 15 source files
```

### Repository checks

```text
git diff --check
```

Result: exit 0. The only output was the repository's existing Windows
LF-to-CRLF working-copy warning for the two modified tracked files.

## Scope and safety confirmation

- No MCP or WEBUI files changed.
- No migrations changed; migrations 001-004 remain untouched and no migration 005
  was added.
- No dependency declarations or lockfiles changed.
- No operation routes, aggregate views, authentication, Tunnel, or Connector work
  was added.
- No production database, including `data/2126/story.db`, was opened, initialized,
  migrated, or written.
- Tests used temporary roots and in-memory SQLite only.
- Tasks 1-3 behavior remains covered by the 64-test full API suite and 138-test CORE
  suite.

## Delivery

Commit subject: `feat: add shared API error contract`

The commit is local only; Task 4 does not push or create a PR.

## Review fix: normalize remaining canon boundary errors

### Finding

Task 4 review found that the generic `NovelMcpError` handler preserved
`details.domain_code`, but `_error_spec()` left the existing
`CanonReasonRequired` and `DeprecatedCanonForbiddenError` classes on the generic
500 `INTERNAL_ERROR` path. Both errors are intentional CORE policy/boundary denials
raised by services included in Phase B, so treating them as unexpected internal
failures made the shared contract incomplete.

The existing CORE semantics were preserved. Both classes now use the same normalized
409 `DEPENDENCY_CONFLICT` mapping as `CanonPolicyError`; CORE classes, messages, and
service behavior were not changed.

### Behavior-level RED

Two parameterized API cases were added first, asserting status 409, the stable
`DEPENDENCY_CONFLICT` API code, each CORE `domain_code`, project scope, and absence of
raw exception text.

```text
uv run pytest -W error tests/test_errors.py -q
........FF.....................
2 failed, 29 passed in 0.75s
```

The failures showed both errors returning 500 instead of 409.

### GREEN and verification

```text
uv run pytest -W error tests/test_errors.py -q
31 passed in 0.53s

uv run pytest -W error -q
66 passed in 2.31s

uv run ruff check .
All checks passed!

uv run ruff format --check .
22 files already formatted

uv run mypy src
Success: no issues found in 15 source files
```

### Re-review evidence

The final source diff is limited to importing the two existing CORE exception
classes, adding them to the existing dependency-conflict branch, and adding their
behavior-level contract cases. The shared `_domain_details()` path supplies
`CANON_REASON_REQUIRED` and `DEPRECATED_CANON_FORBIDDEN`; the fixed public message
comes from `_DEPENDENCY_CONFLICT`, so raw CORE exception messages are not serialized.
No MCP, WEBUI, migration, dependency, service, or production-data code changed.
