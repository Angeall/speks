"""Tests for the Markdown parser with custom tags."""

from pathlib import Path

import pytest

from speks.core.parser import parse_markdown


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with source and docs."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "regles.py").write_text(
        'def evaluer(x: int) -> bool:\n    """Check x."""\n    return x > 0\n',
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    diagrams = tmp_path / "diagrams"
    diagrams.mkdir()
    (diagrams / "seq.puml").write_text("@startuml\nA -> B\n@enduml\n", encoding="utf-8")
    return tmp_path


class TestCodeTag:
    def test_resolves_function(self, workspace: Path) -> None:
        md = workspace / "docs" / "test.md"
        md.write_text("# Test\n\n@[code](src/regles.py:evaluer)\n", encoding="utf-8")
        page = parse_markdown(md, workspace)
        assert "```python" in page.resolved_markdown
        assert "def evaluer" in page.resolved_markdown

    def test_missing_file(self, workspace: Path) -> None:
        md = workspace / "docs" / "test.md"
        md.write_text("@[code](src/missing.py:foo)\n", encoding="utf-8")
        page = parse_markdown(md, workspace)
        assert "file not found" in page.resolved_markdown

    def test_missing_symbol(self, workspace: Path) -> None:
        md = workspace / "docs" / "test.md"
        md.write_text("@[code](src/regles.py:nonexistent)\n", encoding="utf-8")
        page = parse_markdown(md, workspace)
        assert "not found" in page.resolved_markdown


class TestPlantUMLTag:
    def test_resolves_diagram(self, workspace: Path) -> None:
        md = workspace / "docs" / "test.md"
        md.write_text("@[plantuml](diagrams/seq.puml)\n", encoding="utf-8")
        page = parse_markdown(md, workspace)
        assert "```plantuml" in page.resolved_markdown
        assert "@startuml" in page.resolved_markdown


class TestPlaygroundTag:
    def test_creates_placeholder(self, workspace: Path) -> None:
        md = workspace / "docs" / "test.md"
        md.write_text("@[playground](src/regles.py:evaluer)\n", encoding="utf-8")
        page = parse_markdown(md, workspace)
        assert 'class="speks-playground"' in page.resolved_markdown
        assert len(page.playgrounds) == 1
        assert page.playgrounds[0].function_name == "evaluer"
        assert page.playgrounds[0].parameters[0]["name"] == "x"
