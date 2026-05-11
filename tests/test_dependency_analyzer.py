"""Tests for the dependency analyzer (``@service`` / ``@stub`` API)."""

import textwrap
from pathlib import Path

import pytest

from speks.core.dependency_analyzer import (
    DependencyGraph,
    PydanticFieldInfo,
    analyze_directory,
    analyze_file,
    get_service_mock_defaults,
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Multi-file project with two service entities and three business rules."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "services.py").write_text(
        textwrap.dedent("""\
            from speks import service, stub

            @service
            class APIClient:
                \"\"\"Appel HTTP externe.\"\"\"

                @stub(mock="ok")
                def fetch(self, x: str) -> str:
                    \"\"\"Fetch a value.\"\"\"
                    ...

            @service
            class DBService:
                \"\"\"Acces base de donnees.\"\"\"

                @stub(mock=[])
                def query(self, q: str) -> list:
                    \"\"\"Run a query.\"\"\"
                    ...
        """),
        encoding="utf-8",
    )

    (src / "rules.py").write_text(
        textwrap.dedent("""\
            from .services import APIClient, DBService

            def check_user(user_id: str) -> bool:
                \"\"\"Check if user is valid.\"\"\"
                result = APIClient().fetch(user_id)
                return result == "ok"

            def get_history(user_id: str) -> list:
                data = DBService().query(f"SELECT * FROM history WHERE user='{user_id}'")
                return data

            def full_check(user_id: str) -> dict:
                \"\"\"Combines user check and history.\"\"\"
                valid = check_user(user_id)
                history = get_history(user_id)
                return {"valid": valid, "history": history}
        """),
        encoding="utf-8",
    )

    return tmp_path


class TestAnalyzeDirectory:
    def test_finds_stubs(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert "APIClient.fetch" in graph.services
        assert "DBService.query" in graph.services
        assert len(graph.services) == 2

    def test_finds_functions(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert "check_user" in graph.functions
        assert "get_history" in graph.functions
        assert "full_check" in graph.functions

    def test_stub_uses_method_docstring(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient.fetch"].docstring == "Fetch a value."

    def test_detects_stub_calls(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        check_edges = graph.edges_from("check_user")
        assert len(check_edges) == 1
        assert check_edges[0].callee == "APIClient.fetch"
        assert check_edges[0].kind == "service"

    def test_detects_function_calls(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        full_edges = graph.edges_from("full_check")
        callee_names = {e.callee for e in full_edges}
        assert "check_user" in callee_names
        assert "get_history" in callee_names

    def test_edges_kind(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        for edge in graph.edges:
            if edge.callee in graph.services:
                assert edge.kind == "service"
            else:
                assert edge.kind == "function"

    def test_undecorated_class_is_ignored(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import stub

                class NotAService:
                    @stub(mock="x")
                    def method(self) -> str:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services == {}

    def test_method_without_stub_is_ignored(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import service, stub

                @service
                class Mixed:
                    @stub(mock="ok")
                    def fetch(self) -> str:
                        ...

                    def helper(self) -> int:
                        return 42
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert "Mixed.fetch" in graph.services
        assert "Mixed.helper" not in graph.services


class TestTransitiveDeps:
    def test_direct_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        deps = graph.transitive_deps("check_user")
        assert deps == {"APIClient.fetch"}

    def test_transitive_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        deps = graph.transitive_deps("full_check")
        assert "check_user" in deps
        assert "get_history" in deps
        assert "APIClient.fetch" in deps
        assert "DBService.query" in deps

    def test_no_self_in_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        deps = graph.transitive_deps("full_check")
        assert "full_check" not in deps


class TestEdgesTo:
    def test_callers_of_stub(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        callers = graph.edges_to("APIClient.fetch")
        assert len(callers) == 1
        assert callers[0].caller == "check_user"

    def test_callers_of_function(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        callers = graph.edges_to("check_user")
        assert len(callers) == 1
        assert callers[0].caller == "full_check"


class TestMermaidRendering:
    def test_full_graph(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        mermaid = graph.to_mermaid()
        assert "graph LR" in mermaid
        assert "APIClient / fetch" in mermaid
        assert "DBService / query" in mermaid
        assert "classDef service" in mermaid
        assert "classDef func" in mermaid

    def test_focused_graph(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        mermaid = graph.to_mermaid(highlight_func="full_check")
        assert "graph LR" in mermaid
        assert "full_check" in mermaid
        assert "check_user" in mermaid
        assert "APIClient / fetch" in mermaid
        assert "classDef entry" in mermaid

    def test_focused_excludes_unrelated(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        mermaid = graph.to_mermaid(highlight_func="check_user")
        assert "APIClient / fetch" in mermaid
        assert "DBService" not in mermaid

    def test_service_edges_have_method_label(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        mermaid = graph.to_mermaid()
        assert "|.fetch|" in mermaid
        assert "|.query|" in mermaid


class TestAnalyzeFile:
    def test_returns_same_as_directory(self, project: Path) -> None:
        g1 = analyze_directory(project / "src", project)
        g2 = analyze_file(project / "src" / "rules.py", project)
        assert set(g1.services.keys()) == set(g2.services.keys())
        assert set(g1.functions.keys()) == set(g2.functions.keys())


class TestMockDefaultExtraction:
    def test_extracts_scalar(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient.fetch"].mock_data_default == "ok"

    def test_extracts_list(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["DBService.query"].mock_data_default == []

    def test_extracts_dict(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import service, stub

                @service
                class ScoreService:
                    @stub(mock={"score": 720, "incidents": 0})
                    def fetch(self, x: str) -> dict:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["ScoreService.fetch"].mock_data_default == {
            "score": 720,
            "incidents": 0,
        }

    def test_extracts_bool(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import service, stub

                @service
                class BoolService:
                    @stub(mock=False)
                    def check(self, x: str) -> bool:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["BoolService.check"].mock_data_default is False

    def test_none_when_no_literal(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                import time
                from speks import service, stub

                @service
                class DynService:
                    @stub(mock=time.time())
                    def now(self, x: str) -> float:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["DynService.now"].mock_data_default is None


class TestGetServiceMockDefaults:
    def test_returns_defaults_for_function(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        defaults = get_service_mock_defaults(graph, "check_user")
        assert len(defaults) == 1
        assert defaults[0]["name"] == "APIClient.fetch"
        assert defaults[0]["default_json"] == '"ok"'

    def test_returns_transitive_defaults(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        defaults = get_service_mock_defaults(graph, "full_check")
        names = {d["name"] for d in defaults}
        assert names == {"APIClient.fetch", "DBService.query"}

    def test_includes_docstring(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        defaults = get_service_mock_defaults(graph, "check_user")
        assert defaults[0]["docstring"] == "Fetch a value."

    def test_empty_for_no_stub_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        graph.functions["isolated"] = type(graph.functions["check_user"])(
            name="isolated", module="src/rules.py",
        )
        defaults = get_service_mock_defaults(graph, "isolated")
        assert defaults == []

    def test_includes_component_and_method_name(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        defaults = get_service_mock_defaults(graph, "check_user")
        d = defaults[0]
        assert d["component_name"] == "APIClient"
        assert d["method_name"] == "fetch"
        assert d["display_name"] == "APIClient / fetch"

    def test_includes_error_default(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import service, stub, MockError

                @service
                class MyAPI:
                    @stub(
                        mock="ok",
                        error=MockError(
                            error_code="FAIL",
                            error_message="Something went wrong",
                            http_code=500,
                        ),
                    )
                    def do(self, x: str) -> str:
                        ...

                def use_api(x: str) -> str:
                    return MyAPI().do(x)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        defaults = get_service_mock_defaults(graph, "use_api")
        assert len(defaults) == 1
        assert defaults[0]["error_default"] == {
            "error_code": "FAIL",
            "error_message": "Something went wrong",
            "http_code": 500,
        }


class TestMockErrorExtraction:
    def test_extracts_full_mock_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import service, stub, MockError

                @service
                class MySvc:
                    @stub(
                        mock="ok",
                        error=MockError("SVC_DOWN", "Service unavailable", http_code=503),
                    )
                    def do(self, x: str) -> str:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        err = graph.services["MySvc.do"].mock_error_default
        assert err == {
            "error_code": "SVC_DOWN",
            "error_message": "Service unavailable",
            "http_code": 503,
        }

    def test_no_mock_error_returns_none(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient.fetch"].mock_error_default is None

    def test_mock_error_without_http_code(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import service, stub, MockError

                @service
                class MySvc:
                    @stub(
                        mock="ok",
                        error=MockError(
                            error_code="LOGIC_ERR",
                            error_message="Bad input",
                        ),
                    )
                    def do(self, x: str) -> str:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        err = graph.services["MySvc.do"].mock_error_default
        assert err == {
            "error_code": "LOGIC_ERR",
            "error_message": "Bad input",
        }


class TestPydanticMockDetection:
    def test_detects_pydantic_model_fields(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from pydantic import BaseModel
                from speks import service, stub

                class ProductInfo(BaseModel):
                    id: str
                    name: str
                    base_price: float
                    category: str

                @service
                class ProductCatalog:
                    @stub(mock=ProductInfo(
                        id="p1",
                        name="Headphones",
                        base_price=79.99,
                        category="electronics",
                    ))
                    def fetch_product(self, product_id: str) -> ProductInfo:
                        ...

                def get_product(product_id: str) -> dict:
                    return ProductCatalog().fetch_product(product_id)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        svc = graph.services["ProductCatalog.fetch_product"]
        assert svc.mock_pydantic_class == "ProductInfo"
        assert svc.mock_pydantic_fields is not None
        assert len(svc.mock_pydantic_fields) == 4
        names = [f.name for f in svc.mock_pydantic_fields]
        assert names == ["id", "name", "base_price", "category"]
        field_map = {f.name: f for f in svc.mock_pydantic_fields}
        assert field_map["base_price"].annotation == "float"
        assert field_map["id"].annotation == "str"
        assert field_map["id"].default == "p1"
        assert field_map["name"].default == "Headphones"
        assert field_map["base_price"].default == 79.99

    def test_no_pydantic_for_scalar_mock(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient.fetch"].mock_pydantic_fields is None
        assert graph.services["APIClient.fetch"].mock_pydantic_class is None

    def test_pydantic_with_defaults_in_model(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from pydantic import BaseModel
                from speks import service, stub

                class Config(BaseModel):
                    timeout: int = 30
                    retries: int = 3
                    endpoint: str

                @service
                class ConfigAPI:
                    @stub(mock=Config(endpoint="http://api.example.com"))
                    def fetch(self) -> Config:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        svc = graph.services["ConfigAPI.fetch"]
        assert svc.mock_pydantic_class == "Config"
        field_map = {f.name: f for f in svc.mock_pydantic_fields}
        assert field_map["timeout"].default == 30
        assert field_map["retries"].default == 3

    def test_pydantic_fields_in_mock_defaults(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from pydantic import BaseModel
                from speks import service, stub

                class Info(BaseModel):
                    name: str
                    score: float

                @service
                class InfoAPI:
                    @stub(mock=Info(name="test", score=0.95))
                    def fetch(self, x: str) -> Info:
                        ...

                def get_info(x: str) -> dict:
                    return InfoAPI().fetch(x)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        defaults = get_service_mock_defaults(graph, "get_info")
        assert len(defaults) == 1
        assert defaults[0]["pydantic_class"] == "Info"
        assert defaults[0]["pydantic_fields"] is not None
        assert len(defaults[0]["pydantic_fields"]) == 2
        assert defaults[0]["pydantic_fields"][0]["name"] == "name"
        assert defaults[0]["pydantic_fields"][1]["annotation"] == "float"

    def test_non_basemodel_class_not_detected(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import service, stub

                class PlainClass:
                    def __init__(self, x: int):
                        self.x = x

                @service
                class MySvc:
                    @stub(mock=None)
                    def fetch(self) -> int:
                        ...
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["MySvc.fetch"].mock_pydantic_fields is None
