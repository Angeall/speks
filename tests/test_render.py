"""Tests for the standalone render module (speks render)."""

import textwrap
from pathlib import Path

import pytest

from speks.core.render import render_markdown_to_html, resolve_tags


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "regles.py").write_text(
        textwrap.dedent("""\
            def evaluer(x: int) -> bool:
                \"\"\"Check x.\"\"\"
                return x > 0

            def evaluer_avance(client_id: str, montant: float, seuil: int = 600) -> dict:
                \"\"\"Évaluation avancée.\"\"\"
                return {"ok": True}
        """),
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    diagrams = tmp_path / "diagrams"
    diagrams.mkdir()
    (diagrams / "flow.mmd").write_text("graph LR\n    A --> B\n", encoding="utf-8")
    return tmp_path


class TestResolveTags:
    def test_code_tag(self, workspace: Path) -> None:
        md = "# Test\n\n@[code](src/regles.py:evaluer)\n"
        result = resolve_tags(md, workspace)
        assert "```python" in result
        assert "def evaluer" in result

    def test_contract_tag(self, workspace: Path) -> None:
        md = "@[contract](src/regles.py:evaluer_avance)\n"
        result = resolve_tags(md, workspace)
        assert "speks-contract" in result
        assert "<code>client_id</code>" in result
        assert "<code>str</code>" in result
        assert "600" in result

    def test_playground_tag(self, workspace: Path) -> None:
        md = "@[playground](src/regles.py:evaluer)\n"
        result = resolve_tags(md, workspace)
        assert "speks-playground-widget" in result

    def test_mermaid_tag(self, workspace: Path) -> None:
        md = "@[mermaid](diagrams/flow.mmd)\n"
        result = resolve_tags(md, workspace)
        assert "```mermaid" in result

    def test_plantuml_placeholder(self, workspace: Path) -> None:
        md = "@[plantuml](diagrams/seq.puml)\n"
        result = resolve_tags(md, workspace)
        assert "PlantUML" in result

    def test_missing_file(self, workspace: Path) -> None:
        md = "@[code](src/nope.py:foo)\n"
        result = resolve_tags(md, workspace)
        assert "file not found" in result


class TestRenderMarkdownToHtml:
    def test_produces_full_html(self, workspace: Path) -> None:
        md_file = workspace / "docs" / "test.md"
        md_file.write_text("# Hello\n\nSome text.\n", encoding="utf-8")
        html = render_markdown_to_html(md_file, workspace)
        assert "<!DOCTYPE html>" in html
        assert "<h1" in html
        assert "Hello" in html
        assert "</body>" in html

    def test_resolves_code_tag(self, workspace: Path) -> None:
        md_file = workspace / "docs" / "test.md"
        md_file.write_text("@[code](src/regles.py:evaluer)\n", encoding="utf-8")
        html = render_markdown_to_html(md_file, workspace)
        assert "evaluer" in html
        assert "<pre" in html

    def test_resolves_contract_tag(self, workspace: Path) -> None:
        md_file = workspace / "docs" / "test.md"
        md_file.write_text("@[contract](src/regles.py:evaluer_avance)\n", encoding="utf-8")
        html = render_markdown_to_html(md_file, workspace)
        assert "speks-contract" in html
        assert "client_id" in html

    def test_includes_css(self, workspace: Path) -> None:
        md_file = workspace / "docs" / "test.md"
        md_file.write_text("# Test\n", encoding="utf-8")
        html = render_markdown_to_html(md_file, workspace)
        assert "<style>" in html
        assert "speks-contract" in html

    def test_playground_button_disabled(self, workspace: Path) -> None:
        md_file = workspace / "docs" / "test.md"
        md_file.write_text("@[playground](src/regles.py:evaluer)\n", encoding="utf-8")
        html = render_markdown_to_html(md_file, workspace)
        assert "disabled" in html
