"""Tests for the code extractor."""

import textwrap
from pathlib import Path

import pytest

from speks.core.code_extractor import (
    _parse_docstring,
    extract_all_functions,
    extract_class,
    extract_function,
    extract_structured_types,
    parse_tag_arg,
)

SAMPLE_CODE = textwrap.dedent("""\
    class Greeter:
        \"\"\"A greeting class.\"\"\"
        def greet(self, name: str) -> str:
            return f"Hello, {name}"

    def add(a: int, b: int = 0) -> int:
        \"\"\"Add two numbers.\"\"\"
        return a + b

    def multiply(x: float, y: float) -> float:
        return x * y
""")


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(SAMPLE_CODE, encoding="utf-8")
    return p


class TestExtractFunction:
    def test_extracts_named_function(self, sample_file: Path) -> None:
        info = extract_function(sample_file, "add")
        assert info.name == "add"
        assert "return a + b" in info.source
        assert info.docstring == "Add two numbers."

    def test_parameters(self, sample_file: Path) -> None:
        info = extract_function(sample_file, "add")
        assert len(info.parameters) == 2
        assert info.parameters[0].name == "a"
        assert info.parameters[0].annotation == "int"
        assert info.parameters[1].default == "0"

    def test_return_annotation(self, sample_file: Path) -> None:
        info = extract_function(sample_file, "add")
        assert info.return_annotation == "int"

    def test_not_found_raises(self, sample_file: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_function(sample_file, "nonexistent")


class TestExtractClass:
    def test_extracts_class(self, sample_file: Path) -> None:
        src = extract_class(sample_file, "Greeter")
        assert "class Greeter" in src
        assert "def greet" in src

    def test_not_found_raises(self, sample_file: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_class(sample_file, "Missing")


class TestExtractAllFunctions:
    def test_finds_top_level(self, sample_file: Path) -> None:
        funcs = extract_all_functions(sample_file)
        names = [f.name for f in funcs]
        assert "add" in names
        assert "multiply" in names


PYDANTIC_CODE = textwrap.dedent("""\
    from pydantic import BaseModel

    class Address(BaseModel):
        \"\"\"A postal address.\"\"\"
        street: str
        city: str
        zip_code: str
        country: str = "US"

    class Customer(BaseModel):
        \"\"\"A customer record.\"\"\"
        name: str
        age: int
        address: Address
        email: str | None = None
""")

DATACLASS_CODE = textwrap.dedent("""\
    from dataclasses import dataclass

    @dataclass
    class Point:
        \"\"\"A 2D point.\"\"\"
        x: float
        y: float
        label: str = ""
""")


class TestExtractStructuredTypes:
    def test_extracts_pydantic_models(self, tmp_path: Path) -> None:
        p = tmp_path / "models.py"
        p.write_text(PYDANTIC_CODE, encoding="utf-8")
        types = extract_structured_types(p)
        assert "Address" in types
        assert "Customer" in types

    def test_pydantic_fields(self, tmp_path: Path) -> None:
        p = tmp_path / "models.py"
        p.write_text(PYDANTIC_CODE, encoding="utf-8")
        addr = extract_structured_types(p)["Address"]
        names = [f.name for f in addr.fields]
        assert names == ["street", "city", "zip_code", "country"]
        assert addr.fields[0].required is True
        assert addr.fields[3].required is False
        assert addr.fields[3].default == "'US'"

    def test_pydantic_docstring(self, tmp_path: Path) -> None:
        p = tmp_path / "models.py"
        p.write_text(PYDANTIC_CODE, encoding="utf-8")
        addr = extract_structured_types(p)["Address"]
        assert addr.docstring == "A postal address."

    def test_extracts_dataclasses(self, tmp_path: Path) -> None:
        p = tmp_path / "dc.py"
        p.write_text(DATACLASS_CODE, encoding="utf-8")
        types = extract_structured_types(p)
        assert "Point" in types
        pt = types["Point"]
        assert len(pt.fields) == 3
        assert pt.fields[2].default == "''"

    def test_ignores_plain_classes(self, sample_file: Path) -> None:
        types = extract_structured_types(sample_file)
        assert "Greeter" not in types

    def test_extracts_inline_comments(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            from pydantic import BaseModel

            class Order(BaseModel):
                item: str  # Product name
                qty: int  # Quantity ordered
                price: float = 0.0  # Unit price
                note: str = ""
        """)
        p = tmp_path / "order.py"
        p.write_text(code, encoding="utf-8")
        order = extract_structured_types(p)["Order"]
        assert order.fields[0].comment == "Product name"
        assert order.fields[1].comment == "Quantity ordered"
        assert order.fields[2].comment == "Unit price"
        assert order.fields[3].comment is None

    def test_inline_comment_with_hash_in_string(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            from pydantic import BaseModel

            class Config(BaseModel):
                pattern: str = "a#b"  # A regex pattern
                plain: str = "hello"
        """)
        p = tmp_path / "cfg.py"
        p.write_text(code, encoding="utf-8")
        cfg = extract_structured_types(p)["Config"]
        assert cfg.fields[0].comment == "A regex pattern"
        assert cfg.fields[1].comment is None


class TestParseTagArg:
    def test_file_only(self) -> None:
        assert parse_tag_arg("src/file.py") == ("src/file.py", None, "")

    def test_file_and_function(self) -> None:
        assert parse_tag_arg("src/file.py:my_func") == ("src/file.py", None, "my_func")

    def test_file_class_method(self) -> None:
        assert parse_tag_arg("src/file.py:MyClass:execute") == ("src/file.py", "MyClass", "execute")

    def test_nested_path(self) -> None:
        assert parse_tag_arg("src/sub/module.py:Cls:run") == ("src/sub/module.py", "Cls", "run")

    def test_no_py_extension(self) -> None:
        # Directories for @[dependencies]
        assert parse_tag_arg("src/") == ("src/", None, "")


class TestExtractMethod:
    def test_extracts_method_from_class(self, sample_file: Path) -> None:
        info = extract_function(sample_file, "greet", class_name="Greeter")
        assert info.name == "greet"
        assert "Hello" in info.source
        # self should be excluded from parameters
        assert len(info.parameters) == 1
        assert info.parameters[0].name == "name"

    def test_method_not_found_in_class(self, sample_file: Path) -> None:
        with pytest.raises(ValueError, match="Method.*not found.*class.*Greeter"):
            extract_function(sample_file, "nonexistent", class_name="Greeter")

    def test_class_not_found(self, sample_file: Path) -> None:
        with pytest.raises(ValueError, match="Class.*not found"):
            extract_function(sample_file, "greet", class_name="Missing")

    def test_does_not_find_method_at_top_level(self, tmp_path: Path) -> None:
        """Method with same name as a top-level function should be scoped."""
        code = textwrap.dedent("""\
            def run():
                return "top-level"

            class Worker:
                def run(self):
                    return "method"
        """)
        p = tmp_path / "scoped.py"
        p.write_text(code, encoding="utf-8")

        # Without class_name, finds top-level
        info = extract_function(p, "run")
        assert "top-level" in info.source

        # With class_name, finds method
        info = extract_function(p, "run", class_name="Worker")
        assert "method" in info.source


class TestParseDocstring:
    def test_extracts_param_descriptions(self) -> None:
        doc = "Do something.\n\n:param x: The X value\n:param y: The Y value"
        clean, params, ret = _parse_docstring(doc)
        assert clean == "Do something."
        assert params == {"x": "The X value", "y": "The Y value"}
        assert ret is None

    def test_extracts_return_description(self) -> None:
        doc = "Compute it.\n\n:return: The result"
        clean, params, ret = _parse_docstring(doc)
        assert clean == "Compute it."
        assert params == {}
        assert ret == "The result"

    def test_returns_variant(self) -> None:
        doc = "Compute.\n\n:returns: The value"
        _, _, ret = _parse_docstring(doc)
        assert ret == "The value"

    def test_none_docstring(self) -> None:
        clean, params, ret = _parse_docstring(None)
        assert clean is None
        assert params == {}
        assert ret is None

    def test_no_param_lines(self) -> None:
        doc = "Just a description."
        clean, params, ret = _parse_docstring(doc)
        assert clean == "Just a description."
        assert params == {}
        assert ret is None

    def test_mixed(self) -> None:
        doc = "Evaluate credit.\n\nChecks balance and score.\n\n:param id: Client ID\n:param amt: Amount\n:return: Approval status"
        clean, params, ret = _parse_docstring(doc)
        assert clean == "Evaluate credit.\n\nChecks balance and score."
        assert params == {"id": "Client ID", "amt": "Amount"}
        assert ret == "Approval status"


class TestExtractFunctionDocstringParsing:
    def test_param_descriptions_on_parameters(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            def calc(x: int, y: int = 0) -> int:
                \"\"\"Add values.

                :param x: First operand
                :param y: Second operand
                :return: Sum of x and y
                \"\"\"
                return x + y
        """)
        p = tmp_path / "calc.py"
        p.write_text(code, encoding="utf-8")
        info = extract_function(p, "calc")
        assert info.docstring == "Add values."
        assert info.parameters[0].description == "First operand"
        assert info.parameters[1].description == "Second operand"
        assert info.return_description == "Sum of x and y"

    def test_no_param_lines_leaves_none(self, tmp_path: Path) -> None:
        code = textwrap.dedent("""\
            def simple(a: int) -> int:
                \"\"\"Just returns a.\"\"\"
                return a
        """)
        p = tmp_path / "simple.py"
        p.write_text(code, encoding="utf-8")
        info = extract_function(p, "simple")
        assert info.docstring == "Just returns a."
        assert info.parameters[0].description is None
        assert info.return_description is None
