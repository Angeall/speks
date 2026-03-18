"""Tests for the code extractor."""

import textwrap
from pathlib import Path

import pytest

from speks.core.code_extractor import (
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
