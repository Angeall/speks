"""Tests for the MkDocs plugins (tag resolution, playground injection, dependencies)."""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from speks.mkdocs_plugins.tags import SpeksTagsPlugin, _resolve_code, _resolve_plantuml, _resolve_mermaid, _resolve_playground, _resolve_contract
from speks.mkdocs_plugins.playground import SpeksPlaygroundPlugin
from speks.mkdocs_plugins.dependencies import _resolve_dependencies


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "regles.py").write_text(
        textwrap.dedent("""\
            from speks import ExternalService, MockResponse

            class MyService:
                pass

            class SoldeAPI(ExternalService):
                \"\"\"API Solde.\"\"\"
                def execute(self, x: str) -> float:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data=1500.0)

            def evaluer(x: int) -> bool:
                \"\"\"Check x.\"\"\"
                solde = SoldeAPI().call(str(x))
                return solde > 0

            def evaluer_avance(client_id: str, montant: float, seuil: int = 600) -> dict:
                \"\"\"Évaluation avancée combinant solde et score.\"\"\"
                return {"ok": True}
        """),
        encoding="utf-8",
    )
    diagrams = tmp_path / "diagrams"
    diagrams.mkdir()
    (diagrams / "seq.puml").write_text("@startuml\nA -> B\n@enduml\n", encoding="utf-8")
    (diagrams / "flow.mmd").write_text("graph LR\n    A --> B\n    B --> C\n", encoding="utf-8")
    return tmp_path


class TestResolveCode:
    def test_function(self, workspace: Path) -> None:
        result = _resolve_code("src/regles.py:evaluer", workspace)
        assert "```python" in result
        assert "def evaluer" in result

    def test_class(self, workspace: Path) -> None:
        result = _resolve_code("src/regles.py:MyService", workspace)
        assert "class MyService" in result

    def test_whole_file(self, workspace: Path) -> None:
        result = _resolve_code("src/regles.py", workspace)
        assert "class MyService" in result
        assert "def evaluer" in result

    def test_missing_file(self, workspace: Path) -> None:
        result = _resolve_code("src/missing.py:foo", workspace)
        assert "file not found" in result

    def test_missing_symbol(self, workspace: Path) -> None:
        result = _resolve_code("src/regles.py:nonexistent", workspace)
        assert "not found" in result

    def test_class_method(self, workspace: Path) -> None:
        result = _resolve_code("src/regles.py:SoldeAPI:execute", workspace)
        assert "```python" in result
        assert "def execute" in result

    def test_class_method_missing(self, workspace: Path) -> None:
        result = _resolve_code("src/regles.py:SoldeAPI:nonexistent", workspace)
        assert "not found" in result


class TestResolvePlantuml:
    def test_diagram(self, workspace: Path) -> None:
        result = _resolve_plantuml("diagrams/seq.puml", workspace)
        assert "```plantuml" in result
        assert "@startuml" in result

    def test_missing(self, workspace: Path) -> None:
        result = _resolve_plantuml("diagrams/nope.puml", workspace)
        assert "not found" in result


class TestResolveMermaid:
    def test_diagram(self, workspace: Path) -> None:
        result = _resolve_mermaid("diagrams/flow.mmd", workspace)
        assert "```mermaid" in result
        assert "graph LR" in result
        assert "A --> B" in result

    def test_missing(self, workspace: Path) -> None:
        result = _resolve_mermaid("diagrams/nope.mmd", workspace)
        assert "not found" in result


class TestResolvePlayground:
    def test_generates_widget(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "speks-playground-widget" in result
        assert "speks-run-btn" in result
        assert 'data-function="evaluer"' in result

    def test_form_fields(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert 'name="x"' in result
        assert "int" in result

    def test_missing_function(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:nonexistent", workspace)
        assert "not found" in result

    def test_bad_format(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py", workspace)
        assert "requires file:function format" in result

    def test_mock_config_section(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "speks-mock-config" in result
        assert "Mock configuration" in result

    def test_mock_config_contains_service(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "SoldeAPI" in result
        assert 'data-service="SoldeAPI"' in result

    def test_mock_config_default_value(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "1500.0" in result

    def test_mock_config_includes_docstring(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "API Solde" in result

    def test_testcase_panel_rendered(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "speks-testcases" in result
        assert "speks-tc-list" in result

    def test_testcase_panel_shows_saved_cases(self, workspace: Path) -> None:
        import json as json_mod

        tc_dir = workspace / "testcases"
        tc_dir.mkdir()
        (tc_dir / "evaluer.json").write_text(
            json_mod.dumps([
                {"id": "tc-aaa", "name": "my case", "inputs": {"x": 1},
                 "mocks": {}, "expected": True},
            ]),
            encoding="utf-8",
        )
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "my case" in result
        assert "tc-aaa" in result

    def test_save_btn_present_in_mkdocs_mode(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "speks-tc-save-btn" in result
        assert "swSaveTestCase" in result

    def test_error_mock_has_structured_fields(self, workspace: Path) -> None:
        result = _resolve_playground("src/regles.py:evaluer", workspace)
        assert "speks-error-fields" in result
        assert 'data-error-field="error_code"' in result
        assert 'data-error-field="error_message"' in result
        assert 'data-error-field="http_code"' in result
        # Should have default values
        assert 'value="ERR_EXAMPLE"' in result
        assert 'value="Example error"' in result
        assert 'value="500"' in result

    def test_pydantic_mock_renders_individual_fields(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "svc.py").write_text(
            textwrap.dedent("""\
                from pydantic import BaseModel
                from speks import ExternalService, MockResponse

                class ProductInfo(BaseModel):
                    name: str
                    price: float

                class FetchProduct(ExternalService):
                    def execute(self, pid: str) -> ProductInfo:
                        pass
                    def mock(self, pid: str) -> MockResponse:
                        return MockResponse(data=ProductInfo(name="Widget", price=9.99))

                def get_product(pid: str) -> dict:
                    return FetchProduct().call(pid)
            """),
            encoding="utf-8",
        )
        result = _resolve_playground("src/svc.py:get_product", tmp_path)
        assert "speks-mock-pydantic" in result
        assert 'data-field="name"' in result
        assert 'data-field="price"' in result
        assert 'value="Widget"' in result
        assert 'value="9.99"' in result
        # Should NOT have a textarea for this service
        assert 'class="speks-mock-input"' not in result


class TestResolveContract:
    def test_generates_table(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:evaluer", workspace)
        assert "speks-contract" in result
        assert "speks-contract-table" in result
        assert "Inputs" in result
        assert "Output" in result

    def test_shows_param_name_and_type(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:evaluer", workspace)
        assert "<code>x</code>" in result
        assert "<code>int</code>" in result

    def test_shows_return_type(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:evaluer", workspace)
        assert "<code>bool</code>" in result

    def test_shows_default_value(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:evaluer_avance", workspace)
        assert "600" in result

    def test_multiple_params(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:evaluer_avance", workspace)
        assert "<code>client_id</code>" in result
        assert "<code>montant</code>" in result
        assert "<code>seuil</code>" in result
        assert "<code>str</code>" in result
        assert "<code>float</code>" in result
        assert "<code>int</code>" in result

    def test_shows_docstring(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:evaluer_avance", workspace)
        assert "valuation avancée" in result

    def test_shows_function_name(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:evaluer_avance", workspace)
        assert "<code>evaluer_avance</code>" in result

    def test_missing_function(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:nonexistent", workspace)
        assert "not found" in result

    def test_bad_format(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py", workspace)
        assert "requires file:function format" in result

    def test_missing_file(self, workspace: Path) -> None:
        result = _resolve_contract("src/nope.py:func", workspace)
        assert "file not found" in result

    def test_class_method_contract(self, workspace: Path) -> None:
        result = _resolve_contract("src/regles.py:SoldeAPI:execute", workspace)
        assert "speks-contract" in result
        assert "SoldeAPI.execute" in result
        assert "<code>x</code>" in result
        assert "<code>str</code>" in result

    def test_unfolds_structured_types(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "typed.py").write_text(
            'from dataclasses import dataclass\n\n'
            '@dataclass\n'
            'class Request:\n'
            '    """A request."""\n'
            '    name: str\n'
            '    amount: float = 0.0\n\n'
            '@dataclass\n'
            'class Response:\n'
            '    """The result."""\n'
            '    ok: bool\n'
            '    detail: str = ""\n\n'
            'def process(req: Request) -> Response:\n'
            '    """Process it."""\n'
            '    return Response(ok=True)\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/typed.py:process", tmp_path)
        # Should contain the expandable type details
        assert "speks-contract-type-details" in result
        assert "Request" in result
        assert "Response" in result
        assert "name" in result
        assert "amount" in result

    def test_unfolds_optional_type(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "opt.py").write_text(
            'from pydantic import BaseModel\n'
            'from typing import Optional\n\n'
            'class Info(BaseModel):\n'
            '    label: str  # Display label\n'
            '    value: int\n\n'
            'def check(info: Optional[Info]) -> bool:\n'
            '    return True\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/opt.py:check", tmp_path)
        assert "speks-contract-type-details" in result
        assert "Info" in result
        assert "label" in result
        assert "value" in result
        assert "Display label" in result

    def test_unfolds_union_none_type(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "union.py").write_text(
            'from pydantic import BaseModel\n\n'
            'class Payload(BaseModel):\n'
            '    data: str  # Raw data\n\n'
            'def send(p: Payload | None) -> bool:\n'
            '    return True\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/union.py:send", tmp_path)
        assert "speks-contract-type-details" in result
        assert "Payload" in result
        assert "data" in result
        assert "Raw data" in result

    def test_unfolds_list_of_type(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "lst.py").write_text(
            'from pydantic import BaseModel\n\n'
            'class Item(BaseModel):\n'
            '    name: str\n\n'
            'def process(items: list[Item]) -> bool:\n'
            '    return True\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/lst.py:process", tmp_path)
        assert "speks-contract-type-details" in result
        assert "Item" in result
        assert "name" in result

    def test_displays_param_descriptions_from_docstring(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "documented.py").write_text(
            'def check(client_id: str, amount: float, threshold: int = 600) -> bool:\n'
            '    """Check credit eligibility.\n'
            '\n'
            '    :param client_id: Unique client identifier\n'
            '    :param amount: Requested credit amount\n'
            '    :param threshold: Minimum score required\n'
            '    :return: True if eligible\n'
            '    """\n'
            '    return True\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/documented.py:check", tmp_path)
        # Param descriptions should appear in the table
        assert "Unique client identifier" in result
        assert "Requested credit amount" in result
        assert "Minimum score required" in result
        # Return description should appear
        assert "True if eligible" in result
        # :param lines should NOT appear in the docstring area
        assert ":param" not in result
        assert ":return" not in result
        # Clean docstring should still be present
        assert "Check credit eligibility." in result

    def test_displays_field_comments(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "commented.py").write_text(
            'from pydantic import BaseModel\n\n'
            'class Request(BaseModel):\n'
            '    client_id: str  # Identifiant du client\n'
            '    amount: float  # Montant demandé\n'
            '    note: str = ""\n\n'
            'def evaluate(req: Request) -> bool:\n'
            '    return True\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/commented.py:evaluate", tmp_path)
        assert "speks-contract-field-comment" in result
        assert "Identifiant du client" in result
        assert "Montant demandé" in result


    def test_unfolds_nested_type_from_subdirectory(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        sub = src / "sub"
        sub.mkdir(parents=True)
        (sub / "__init__.py").write_text("", encoding="utf-8")
        (sub / "types.py").write_text(
            'from pydantic import BaseModel\n\n'
            'class Inner(BaseModel):\n'
            '    value: int\n',
            encoding="utf-8",
        )
        (src / "__init__.py").write_text("", encoding="utf-8")
        (src / "main.py").write_text(
            'from pydantic import BaseModel\n'
            'from .sub.types import Inner\n\n'
            'class Outer(BaseModel):\n'
            '    inner: Inner\n'
            '    label: str\n\n'
            'def process(data: Outer) -> bool:\n'
            '    return True\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/main.py:process", tmp_path)
        assert "speks-contract-type-details" in result
        assert "Outer" in result
        assert "Inner" in result
        assert "value" in result

    def test_unfolds_transitive_nested_types(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        sub = src / "sub"
        sub.mkdir(parents=True)
        (sub / "__init__.py").write_text("", encoding="utf-8")
        (sub / "deep.py").write_text(
            'from pydantic import BaseModel\n\n'
            'class C(BaseModel):\n'
            '    z: str\n',
            encoding="utf-8",
        )
        (sub / "mid.py").write_text(
            'from pydantic import BaseModel\n'
            'from .deep import C\n\n'
            'class B(BaseModel):\n'
            '    x: int\n'
            '    c: C\n',
            encoding="utf-8",
        )
        (src / "__init__.py").write_text("", encoding="utf-8")
        (src / "entry.py").write_text(
            'from pydantic import BaseModel\n'
            'from .sub.mid import B\n\n'
            'class A(BaseModel):\n'
            '    b: B\n'
            '    y: int\n\n'
            'def run(a: A) -> str:\n'
            '    return "ok"\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/entry.py:run", tmp_path)
        assert result.count("speks-contract-type-details") == 3
        assert "A" in result
        assert "B" in result
        assert "C" in result

    def test_unfolds_type_inheriting_from_model(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "inherit.py").write_text(
            'from pydantic import BaseModel\n\n'
            'class Base(BaseModel):\n'
            '    x: int\n\n'
            'class Child(Base):\n'
            '    y: str\n\n'
            'def check(c: Child) -> bool:\n'
            '    return True\n',
            encoding="utf-8",
        )
        result = _resolve_contract("src/inherit.py:check", tmp_path)
        assert "speks-contract-type-details" in result
        assert "Child" in result
        assert "y" in result


class TestPlaygroundPlugin:
    def test_injects_js(self) -> None:
        plugin = SpeksPlaygroundPlugin()
        html = '<html><head></head><body><div class="speks-playground-widget"></div></body></html>'
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        assert "swRunFunction" in result
        # CSS is now served via extra_css, not inline <style>
        assert "<style>" not in result

    def test_skips_non_playground_pages(self) -> None:
        plugin = SpeksPlaygroundPlugin()
        html = "<html><head></head><body><p>Normal page</p></body></html>"
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        assert result == html

    def test_js_collects_mock_overrides(self) -> None:
        plugin = SpeksPlaygroundPlugin()
        html = '<html><head></head><body><div class="speks-playground-widget"></div></body></html>'
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        assert "mockOverrides" in result
        assert "mock_overrides" in result
        assert "speks-mock-input" in result

    def test_skips_contract_only_pages(self) -> None:
        plugin = SpeksPlaygroundPlugin()
        html = '<html><head></head><body><div class="speks-contract"></div></body></html>'
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        # Contract-only pages get no JS injection
        assert "swRunFunction" not in result
        assert result == html

    def test_injects_js_when_both_playground_and_contract(self) -> None:
        plugin = SpeksPlaygroundPlugin()
        html = (
            '<html><head></head><body>'
            '<div class="speks-playground-widget"></div>'
            '<div class="speks-contract"></div>'
            '</body></html>'
        )
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        assert "speks-playground-widget" in result
        assert "swRunFunction" in result

    def test_on_config_registers_extra_css(self, tmp_path: Path) -> None:
        plugin = SpeksPlaygroundPlugin()
        config = MagicMock()
        extra_css: list[str] = []
        theme: dict[str, object] = {}
        config.__getitem__ = lambda self, k: {
            "docs_dir": str(tmp_path),
            "extra_css": extra_css,
            "theme": theme,
        }[k]
        config.get = lambda k, default=None: {
            "extra_css": extra_css,
            "theme": theme,
        }.get(k, default)
        plugin.on_config(config)
        assert "assets/speks.css" in extra_css
        assert (tmp_path / "assets" / "speks.css").exists()
        assert theme.get("logo") == "assets/logo-white.svg"
        assert theme.get("favicon") == "assets/logo.svg"


# ---------------------------------------------------------------------------
# Dependencies plugin
# ---------------------------------------------------------------------------


@pytest.fixture()
def dep_workspace(tmp_path: Path) -> Path:
    """Workspace with services and cross-function calls."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "services.py").write_text(
        textwrap.dedent("""\
            from speks import ExternalService, MockResponse

            class PaymentAPI(ExternalService):
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="ok")

            class FraudCheck(ExternalService):
                def execute(self, x: str) -> bool:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data=False)
        """),
        encoding="utf-8",
    )
    (src / "logic.py").write_text(
        textwrap.dedent("""\
            from .services import PaymentAPI, FraudCheck

            def validate(user_id: str) -> bool:
                return not FraudCheck().call(user_id)

            def process_payment(user_id: str, amount: float) -> dict:
                ok = validate(user_id)
                if ok:
                    PaymentAPI().call(user_id)
                return {"processed": ok}
        """),
        encoding="utf-8",
    )
    return tmp_path


class TestResolveDependencies:
    def test_full_directory(self, dep_workspace: Path) -> None:
        result = _resolve_dependencies("src/", dep_workspace)
        assert "```mermaid" in result
        assert "PaymentAPI" in result
        assert "FraudCheck" in result
        assert "validate" in result
        assert "process_payment" in result

    def test_focused_function(self, dep_workspace: Path) -> None:
        result = _resolve_dependencies("src/logic.py:process_payment", dep_workspace)
        assert "```mermaid" in result
        assert "process_payment" in result
        assert "validate" in result
        assert "FraudCheck" in result
        assert "PaymentAPI" in result
        assert "classDef entry" in result

    def test_focused_leaf_function(self, dep_workspace: Path) -> None:
        result = _resolve_dependencies("src/logic.py:validate", dep_workspace)
        assert "```mermaid" in result
        assert "FraudCheck" in result
        # validate doesn't call PaymentAPI
        assert "PaymentAPI" not in result

    def test_missing_path(self, dep_workspace: Path) -> None:
        result = _resolve_dependencies("nonexistent/", dep_workspace)
        assert "not found" in result

    def test_missing_function(self, dep_workspace: Path) -> None:
        result = _resolve_dependencies("src/logic.py:nonexistent", dep_workspace)
        assert "not found" in result

    def test_legend_included(self, dep_workspace: Path) -> None:
        result = _resolve_dependencies("src/", dep_workspace)
        assert "Legend" in result
        assert "External service" in result
