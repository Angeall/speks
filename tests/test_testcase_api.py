"""Tests for test-case API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from speks.web.server import create_app


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Minimal project directory."""
    (tmp_path / "speks.toml").write_text(
        '[project]\nname = "t"\ntestcases_dir = "testcases"\n',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "rules.py").write_text(
        "def greet(name: str) -> str:\n    return 'hi ' + name\n",
        encoding="utf-8",
    )
    site = tmp_path / "site"
    site.mkdir()
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    app = create_app(project, project / "site")
    return TestClient(app)


class TestTestCaseAPI:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/testcases/greet")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list(self, client: TestClient) -> None:
        resp = client.post("/api/testcases/greet", json={
            "name": "basic",
            "inputs": {"name": "World"},
            "mocks": {},
            "expected": "hi World",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"].startswith("tc-")
        assert body["name"] == "basic"

        resp2 = client.get("/api/testcases/greet")
        assert len(resp2.json()) == 1

    def test_delete(self, client: TestClient) -> None:
        resp = client.post("/api/testcases/greet", json={
            "name": "to-delete",
            "inputs": {"name": "x"},
            "expected": "hi x",
        })
        tc_id = resp.json()["id"]

        del_resp = client.delete(f"/api/testcases/greet/{tc_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] == tc_id

        assert client.get("/api/testcases/greet").json() == []

    def test_delete_not_found(self, client: TestClient) -> None:
        resp = client.delete("/api/testcases/greet/no-such-id")
        assert resp.status_code == 404
