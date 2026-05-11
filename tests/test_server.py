"""Tests for the dev server module loading."""

from pathlib import Path

import pytest

from speks.web.server import _load_user_modules, _find_function, _make_json_safe


@pytest.fixture()
def src_with_relative_imports(tmp_path: Path) -> Path:
    """Create a src/ directory where one module uses a relative import."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "base.py").write_text(
        "def helper(x: int) -> int:\n    return x + 1\n",
        encoding="utf-8",
    )
    (src / "consumer.py").write_text(
        "from .base import helper\n\n"
        "def compute(x: int) -> int:\n"
        '    """Uses helper from sibling module."""\n'
        "    return helper(x) * 2\n",
        encoding="utf-8",
    )
    return src


class TestLoadUserModules:
    def test_loads_simple_module(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "simple.py").write_text(
            "def greet(name: str) -> str:\n    return 'hi ' + name\n",
            encoding="utf-8",
        )
        modules = _load_user_modules(src)
        assert "simple" in modules
        assert _find_function("greet", modules) is not None

    def test_relative_imports_resolve(self, src_with_relative_imports: Path) -> None:
        modules = _load_user_modules(src_with_relative_imports)
        assert "base" in modules
        assert "consumer" in modules, (
            "Module with relative import should load successfully"
        )

    def test_function_from_relative_import_module_works(
        self, src_with_relative_imports: Path
    ) -> None:
        modules = _load_user_modules(src_with_relative_imports)
        compute = _find_function("compute", modules)
        assert compute is not None
        assert compute(3) == 8  # helper(3)=4, 4*2=8


class TestMakeJsonSafe:
    def test_pydantic_model_to_dict(self) -> None:
        from pydantic import BaseModel

        class Foo(BaseModel):
            x: int
            name: str

        result = _make_json_safe(Foo(x=1, name="bar"))
        assert result == {"x": 1, "name": "bar"}

    def test_nested_pydantic_in_list(self) -> None:
        from pydantic import BaseModel

        class Item(BaseModel):
            val: int

        result = _make_json_safe([Item(val=1), Item(val=2)])
        assert result == [{"val": 1}, {"val": 2}]

    def test_nested_pydantic_in_dict(self) -> None:
        from pydantic import BaseModel

        class Item(BaseModel):
            val: int

        result = _make_json_safe({"key": Item(val=42)})
        assert result == {"key": {"val": 42}}

    def test_plain_primitives_unchanged(self) -> None:
        assert _make_json_safe(42) == 42
        assert _make_json_safe("hello") == "hello"
        assert _make_json_safe(None) is None
        assert _make_json_safe([1, 2]) == [1, 2]

    def test_dataclass_converted(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class Dc:
            a: int
            b: str

        assert _make_json_safe(Dc(a=1, b="x")) == {"a": 1, "b": "x"}


# ---------------------------------------------------------------------------
# /api/run end-to-end with @service / @stub
# ---------------------------------------------------------------------------


@pytest.fixture()
def stub_project(tmp_path: Path) -> Path:
    """A minimal project that uses the new @service / @stub API."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "rules.py").write_text(
        "from speks import service, stub, MockError, ServiceError\n"
        "\n"
        "@service\n"
        "class CoreBanking:\n"
        "    @stub(\n"
        "        mock=1500.0,\n"
        '        error=MockError("CLIENT_NOT_FOUND", "not found", http_code=404),\n'
        "    )\n"
        "    def check_balance(self, client_id: str) -> float:\n"
        "        ...\n"
        "\n"
        "def evaluate_credit(client_id: str, amount: float) -> bool:\n"
        "    try:\n"
        "        balance = CoreBanking().check_balance(client_id)\n"
        "    except ServiceError:\n"
        "        return False\n"
        "    return balance > amount\n",
        encoding="utf-8",
    )
    return tmp_path


class TestRunEndpoint:
    def _client(self, project: Path):
        from fastapi.testclient import TestClient

        from speks.web.server import create_app

        app = create_app(project, project / "site")
        return TestClient(app)

    def test_run_default_mock(self, stub_project: Path) -> None:
        client = self._client(stub_project)
        resp = client.post(
            "/api/run",
            json={
                "function": "evaluate_credit",
                "args": {"client_id": "u1", "amount": 1000.0},
                "mock_overrides": {},
                "error_overrides": {},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["result"] is True

    def test_run_with_dotted_mock_override(self, stub_project: Path) -> None:
        client = self._client(stub_project)
        resp = client.post(
            "/api/run",
            json={
                "function": "evaluate_credit",
                "args": {"client_id": "u1", "amount": 1000.0},
                "mock_overrides": {"CoreBanking.check_balance": 100.0},
                "error_overrides": {},
            },
        )
        body = resp.json()
        assert body["success"] is True
        assert body["result"] is False  # 100 < 1000

    def test_run_with_dotted_error_override(self, stub_project: Path) -> None:
        client = self._client(stub_project)
        resp = client.post(
            "/api/run",
            json={
                "function": "evaluate_credit",
                "args": {"client_id": "u1", "amount": 1000.0},
                "mock_overrides": {},
                "error_overrides": {
                    "CoreBanking.check_balance": {
                        "error_code": "TIMEOUT",
                        "error_message": "Timed out",
                        "http_code": 504,
                    }
                },
            },
        )
        body = resp.json()
        # The user code catches ServiceError and returns False, so success=True.
        assert body["success"] is True
        assert body["result"] is False
        # The call log should record the error.
        assert any(
            entry.get("error", {}).get("error_code") == "TIMEOUT"
            for entry in body["call_log"]
        )

    def test_call_log_uses_dotted_service_name(self, stub_project: Path) -> None:
        client = self._client(stub_project)
        resp = client.post(
            "/api/run",
            json={
                "function": "evaluate_credit",
                "args": {"client_id": "u1", "amount": 100.0},
                "mock_overrides": {},
                "error_overrides": {},
            },
        )
        body = resp.json()
        services = [entry["service"] for entry in body["call_log"]]
        assert "CoreBanking.check_balance" in services
