from __future__ import annotations

from pathlib import Path

SRC_LINE_LIMIT = 600
SRC_SIZE_LIMIT = 40 * 1024
TEST_LINE_LIMIT = 800
COMPONENT_NAMES = ("CORE", "API", "MCP")


def _count_lines(path: Path) -> int:
    return path.read_text(encoding="utf-8").count("\n")


def _collect_failures(
    files: list[Path], *, line_limit: int, size_limit: int | None
) -> list[str]:
    failures: list[str] = []
    for path in files:
        line_count = _count_lines(path)
        if line_count > line_limit:
            failures.append(f"{path}: {line_count} lines exceeds {line_limit}")
        if size_limit is not None:
            size = path.stat().st_size
            if size > size_limit:
                failures.append(f"{path}: {size} bytes exceeds {size_limit}")
    return failures


def collect_failures(repo_root: Path) -> list[str]:
    component_roots = tuple(repo_root / name for name in COMPONENT_NAMES)
    src_files = sorted(
        path
        for component_root in component_roots
        for path in component_root.glob("src/**/*.py")
    )
    test_files = sorted(
        path
        for component_root in component_roots
        for path in component_root.glob("tests/**/*.py")
    )
    failures = _collect_failures(
        src_files, line_limit=SRC_LINE_LIMIT, size_limit=SRC_SIZE_LIMIT
    )
    failures.extend(
        _collect_failures(test_files, line_limit=TEST_LINE_LIMIT, size_limit=None)
    )
    return failures


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    failures = collect_failures(repo_root)
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print("source-size checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
