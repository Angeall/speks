"""Tests for /api/run endpoint: timeout and concurrency."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from speks.web.server import create_app


@pytest.fixture()
def project_with_slow_func(tmp_path: Path) -> Path:
    """Project with a fast and a slow (blocking) function."""
    (tmp_path / "speks.toml").write_text(
        '[project]\nname = "t"\nrun_timeout = 2\n',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "funcs.py").write_text(
        "import time\n\n"
        "def fast(x: int) -> int:\n"
        "    return x * 2\n\n"
        "def slow() -> str:\n"
        "    time.sleep(30)\n"
        "    return 'done'\n",
        encoding="utf-8",
    )
    site = tmp_path / "site"
    site.mkdir()
    return tmp_path


@pytest.fixture()
def client(project_with_slow_func: Path) -> TestClient:
    app = create_app(project_with_slow_func, project_with_slow_func / "site")
    return TestClient(app)


class TestRunTimeout:
    def test_fast_function_succeeds(self, client: TestClient) -> None:
        resp = client.post("/api/run", json={
            "function": "fast",
            "args": {"x": "5"},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["result"] == 10

    def test_slow_function_times_out(self, client: TestClient) -> None:
        start = time.monotonic()
        resp = client.post("/api/run", json={
            "function": "slow",
            "args": {},
        })
        elapsed = time.monotonic() - start
        assert resp.status_code == 504
        body = resp.json()
        assert body["success"] is False
        assert "timeout" in body["error"].lower()
        # Should return within ~2s (the configured timeout), not 30s
        assert elapsed < 5

    def test_concurrent_fast_requests(self, client: TestClient) -> None:
        """Multiple /api/run requests execute concurrently."""
        def call(val: int) -> dict:
            resp = client.post("/api/run", json={
                "function": "fast",
                "args": {"x": str(val)},
            })
            return resp.json()

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(call, i) for i in range(3)]
            results = [f.result() for f in as_completed(futures)]

        assert all(r["success"] for r in results)
        returned_values = sorted(r["result"] for r in results)
        assert returned_values == [0, 2, 4]
