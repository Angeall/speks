"""Tests for the dependency analyzer."""

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
    """Create a multi-file project with cross-module dependencies."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "services.py").write_text(
        textwrap.dedent("""\
            from speks import ExternalService, MockResponse

            class APIClient(ExternalService):
                \"\"\"Appel HTTP externe.\"\"\"
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="ok")

            class DBService(ExternalService):
                \"\"\"Accès base de données.\"\"\"
                def execute(self, query: str) -> list:
                    pass
                def mock(self, query: str) -> MockResponse:
                    return MockResponse(data=[])
        """),
        encoding="utf-8",
    )

    (src / "rules.py").write_text(
        textwrap.dedent("""\
            from .services import APIClient, DBService

            def check_user(user_id: str) -> bool:
                \"\"\"Check if user is valid.\"\"\"
                result = APIClient().call(user_id)
                return result == "ok"

            def get_history(user_id: str) -> list:
                data = DBService().call(f"SELECT * FROM history WHERE user='{user_id}'")
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
    def test_finds_services(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert "APIClient" in graph.services
        assert "DBService" in graph.services
        assert len(graph.services) == 2

    def test_finds_functions(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert "check_user" in graph.functions
        assert "get_history" in graph.functions
        assert "full_check" in graph.functions

    def test_service_docstring(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient"].docstring == "Appel HTTP externe."

    def test_detects_service_calls(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        check_edges = graph.edges_from("check_user")
        assert len(check_edges) == 1
        assert check_edges[0].callee == "APIClient"
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


class TestTransitiveDeps:
    def test_direct_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        deps = graph.transitive_deps("check_user")
        assert deps == {"APIClient"}

    def test_transitive_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        deps = graph.transitive_deps("full_check")
        assert "check_user" in deps
        assert "get_history" in deps
        assert "APIClient" in deps
        assert "DBService" in deps

    def test_no_self_in_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        deps = graph.transitive_deps("full_check")
        assert "full_check" not in deps


class TestEdgesTo:
    def test_callers_of_service(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        callers = graph.edges_to("APIClient")
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
        assert "APIClient" in mermaid
        assert "DBService" in mermaid
        assert "classDef service" in mermaid
        assert "classDef func" in mermaid

    def test_focused_graph(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        mermaid = graph.to_mermaid(highlight_func="full_check")
        assert "graph LR" in mermaid
        assert "full_check" in mermaid
        assert "check_user" in mermaid
        assert "APIClient" in mermaid
        assert "classDef entry" in mermaid

    def test_focused_excludes_unrelated(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        mermaid = graph.to_mermaid(highlight_func="check_user")
        # check_user only depends on APIClient, not DBService
        assert "APIClient" in mermaid
        assert "DBService" not in mermaid

    def test_service_edges_have_call_label(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        mermaid = graph.to_mermaid()
        assert "|.call|" in mermaid


class TestAnalyzeFile:
    def test_returns_same_as_directory(self, project: Path) -> None:
        g1 = analyze_directory(project / "src", project)
        g2 = analyze_file(project / "src" / "rules.py", project)
        assert set(g1.services.keys()) == set(g2.services.keys())
        assert set(g1.functions.keys()) == set(g2.functions.keys())


class TestMockDefaultExtraction:
    def test_extracts_scalar(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient"].mock_data_default == "ok"

    def test_extracts_list(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["DBService"].mock_data_default == []

    def test_extracts_complex_types(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class ScoreService(ExternalService):
                    def execute(self, x: str) -> dict:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data={"score": 720, "incidents": 0})
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["ScoreService"].mock_data_default == {"score": 720, "incidents": 0}

    def test_extracts_bool(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class BoolService(ExternalService):
                    def execute(self, x: str) -> bool:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data=False)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["BoolService"].mock_data_default is False

    def test_none_when_no_literal(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse
                import time

                class DynService(ExternalService):
                    def execute(self, x: str) -> float:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data=time.time())
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["DynService"].mock_data_default is None


class TestGetServiceMockDefaults:
    def test_returns_defaults_for_function(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        defaults = get_service_mock_defaults(graph, "check_user")
        assert len(defaults) == 1
        assert defaults[0]["name"] == "APIClient"
        assert defaults[0]["default_json"] == '"ok"'

    def test_returns_transitive_defaults(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        defaults = get_service_mock_defaults(graph, "full_check")
        names = {d["name"] for d in defaults}
        assert names == {"APIClient", "DBService"}

    def test_includes_docstring(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        defaults = get_service_mock_defaults(graph, "check_user")
        assert defaults[0]["docstring"] == "Appel HTTP externe."

    def test_empty_for_no_service_deps(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        # A function with no service dependencies (hypothetical)
        graph.functions["isolated"] = type(graph.functions["check_user"])(
            name="isolated", module="src/rules.py"
        )
        defaults = get_service_mock_defaults(graph, "isolated")
        assert defaults == []

    def test_includes_component_name(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class MyAPI(ExternalService):
                    component_name = "AppA"
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="ok")

                def use_api(x: str) -> str:
                    return MyAPI().call(x)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        defaults = get_service_mock_defaults(graph, "use_api")
        assert len(defaults) == 1
        assert defaults[0]["component_name"] == "AppA"
        assert defaults[0]["display_name"] == "AppA / MyAPI"

    def test_includes_error_default(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse, MockErrorResponse

                class MyAPI(ExternalService):
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="ok")
                    def mock_error(self, x: str) -> MockErrorResponse:
                        return MockErrorResponse(
                            error_code="FAIL",
                            error_message="Something went wrong",
                            http_code=500,
                        )

                def use_api(x: str) -> str:
                    return MyAPI().call(x)
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


class TestComponentName:
    def test_extracts_component_name(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class SvcA(ExternalService):
                    component_name = "AppX"
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="a")

                class SvcB(ExternalService):
                    component_name = "AppX"
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="b")

                class SvcC(ExternalService):
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="c")
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["SvcA"].component_name == "AppX"
        assert graph.services["SvcB"].component_name == "AppX"
        assert graph.services["SvcC"].component_name is None

    def test_display_name_with_component(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class MySvc(ExternalService):
                    component_name = "MyApp"
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="ok")
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["MySvc"].display_name == "MyApp / MySvc"

    def test_display_name_without_component(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient"].display_name == "APIClient"

    def test_mermaid_uses_display_name(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class MySvc(ExternalService):
                    component_name = "AppZ"
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="ok")

                def use_svc(x: str) -> str:
                    return MySvc().call(x)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        mermaid = graph.to_mermaid()
        assert "AppZ / MySvc" in mermaid

    def test_focused_mermaid_uses_display_name(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class MySvc(ExternalService):
                    component_name = "AppZ"
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="ok")

                def use_svc(x: str) -> str:
                    return MySvc().call(x)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        mermaid = graph.to_mermaid(highlight_func="use_svc")
        assert "AppZ / MySvc" in mermaid


class TestMockErrorExtraction:
    def test_extracts_mock_error_default(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse, MockErrorResponse

                class MySvc(ExternalService):
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="ok")
                    def mock_error(self, x: str) -> MockErrorResponse:
                        return MockErrorResponse(
                            error_code="SVC_DOWN",
                            error_message="Service unavailable",
                            http_code=503,
                        )
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        err = graph.services["MySvc"].mock_error_default
        assert err == {
            "error_code": "SVC_DOWN",
            "error_message": "Service unavailable",
            "http_code": 503,
        }

    def test_no_mock_error_returns_none(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient"].mock_error_default is None

    def test_mock_error_without_http_code(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse, MockErrorResponse

                class MySvc(ExternalService):
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="ok")
                    def mock_error(self, x: str) -> MockErrorResponse:
                        return MockErrorResponse(
                            error_code="LOGIC_ERR",
                            error_message="Bad input",
                        )
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        err = graph.services["MySvc"].mock_error_default
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
                from speks import ExternalService, MockResponse

                class ProductInfo(BaseModel):
                    id: str
                    name: str
                    base_price: float
                    category: str

                class FetchProduct(ExternalService):
                    def execute(self, product_id: str) -> ProductInfo:
                        pass
                    def mock(self, product_id: str) -> MockResponse:
                        return MockResponse(data=ProductInfo(
                            id="p1",
                            name="Headphones",
                            base_price=79.99,
                            category="electronics",
                        ))

                def get_product(product_id: str) -> dict:
                    return FetchProduct().call(product_id)
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        svc = graph.services["FetchProduct"]
        assert svc.mock_pydantic_class == "ProductInfo"
        assert svc.mock_pydantic_fields is not None
        assert len(svc.mock_pydantic_fields) == 4
        field_names = [f.name for f in svc.mock_pydantic_fields]
        assert field_names == ["id", "name", "base_price", "category"]
        # Check annotations
        field_map = {f.name: f for f in svc.mock_pydantic_fields}
        assert field_map["base_price"].annotation == "float"
        assert field_map["id"].annotation == "str"
        # Check defaults from constructor call
        assert field_map["id"].default == "p1"
        assert field_map["name"].default == "Headphones"
        assert field_map["base_price"].default == 79.99

    def test_no_pydantic_for_regular_mock(self, project: Path) -> None:
        graph = analyze_directory(project / "src", project)
        assert graph.services["APIClient"].mock_pydantic_fields is None
        assert graph.services["APIClient"].mock_pydantic_class is None

    def test_pydantic_with_defaults_in_model(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from pydantic import BaseModel
                from speks import ExternalService, MockResponse

                class Config(BaseModel):
                    timeout: int = 30
                    retries: int = 3
                    endpoint: str

                class FetchConfig(ExternalService):
                    def execute(self) -> Config:
                        pass
                    def mock(self) -> MockResponse:
                        return MockResponse(data=Config(endpoint="http://api.example.com"))
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        svc = graph.services["FetchConfig"]
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
                from speks import ExternalService, MockResponse

                class Info(BaseModel):
                    name: str
                    score: float

                class FetchInfo(ExternalService):
                    def execute(self, x: str) -> Info:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data=Info(name="test", score=0.95))

                def get_info(x: str) -> dict:
                    return FetchInfo().call(x)
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
                from speks import ExternalService, MockResponse

                class PlainClass:
                    def __init__(self, x: int):
                        self.x = x

                class MySvc(ExternalService):
                    def execute(self) -> int:
                        pass
                    def mock(self) -> MockResponse:
                        return MockResponse(data=PlainClass(x=42))
            """),
            encoding="utf-8",
        )
        graph = analyze_directory(src, tmp_path)
        assert graph.services["MySvc"].mock_pydantic_fields is None
