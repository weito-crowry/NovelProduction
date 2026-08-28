from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "API"


@pytest.fixture
def api_url(tmp_path: Path) -> Iterator[str]:
    data_root = tmp_path / "api-data"
    port = _unused_port()
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "--project",
            str(API_ROOT),
            "novel-api",
            "--data-root",
            str(data_root),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("novel-api exited before health became ready")
            try:
                response = httpx.get(f"{url}/api/v1/health", timeout=1)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("novel-api health did not become ready")
        yield url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def _unused_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
