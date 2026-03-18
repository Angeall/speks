"""Tests for the site builder (MkDocs-based)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from speks.web.builder import build_site, _copy_logo_if_present, _ensure_mkdocs_yml
from speks.core.config import ProjectConfig


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a full project workspace for MkDocs building."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "regles.py").write_text(
        'def evaluer(x: int) -> bool:\n    """Check x."""\n    return x > 0\n',
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text(
        "# Welcome\n\nHello world.\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "intro.md").write_text(
        "# Introduction\n\nHello world.\n\n@[code](src/regles.py:evaluer)\n\n"
        "@[playground](src/regles.py:evaluer)\n",
        encoding="utf-8",
    )
    (tmp_path / "diagrams").mkdir()
    (tmp_path / "speks.toml").write_text(
        '[project]\nname = "Test Project"\n',
        encoding="utf-8",
    )
    return tmp_path


class TestEnsureMkdocsYml:
    def test_generates_yml(self, tmp_path: Path) -> None:
        config = ProjectConfig(project_name="MyProj")
        _ensure_mkdocs_yml(tmp_path, config)
        yml = tmp_path / "mkdocs.yml"
        assert yml.exists()
        content = yml.read_text()
        assert "MyProj" in content
        assert "speks-tags" in content
        assert "material" in content

    def test_includes_logo_when_packaged(self, tmp_path: Path) -> None:
        fake_logo = tmp_path / "fake_logo.svg"
        fake_logo.write_text("<svg/>", encoding="utf-8")
        config = ProjectConfig(project_name="LogoProj")
        with patch("speks.web.builder._get_packaged_asset", return_value=fake_logo):
            _ensure_mkdocs_yml(tmp_path, config)
        content = (tmp_path / "mkdocs.yml").read_text()
        assert "logo: assets/logo-white.svg" in content
        assert "favicon: assets/logo.svg" in content

    def test_no_logo_lines_when_no_package_logo(self, tmp_path: Path) -> None:
        config = ProjectConfig(project_name="NoLogo")
        with patch("speks.web.builder._get_packaged_asset", return_value=None):
            _ensure_mkdocs_yml(tmp_path, config)
        content = (tmp_path / "mkdocs.yml").read_text()
        assert "logo:" not in content

    def test_does_not_overwrite(self, tmp_path: Path) -> None:
        yml = tmp_path / "mkdocs.yml"
        yml.write_text("existing", encoding="utf-8")
        config = ProjectConfig()
        _ensure_mkdocs_yml(tmp_path, config)
        assert yml.read_text() == "existing"


class TestCopyLogo:
    def test_copies_packaged_logos_to_docs_assets(self, tmp_path: Path) -> None:
        fake_logo = tmp_path / "logo.svg"
        fake_logo.write_text("<svg>test</svg>", encoding="utf-8")
        fake_white = tmp_path / "logo-white.svg"
        fake_white.write_text("<svg>white</svg>", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        config = ProjectConfig()

        def fake_asset(name: str) -> Path | None:
            p = tmp_path / name
            return p if p.is_file() else None

        with patch("speks.web.builder._get_packaged_asset", side_effect=fake_asset):
            _copy_logo_if_present(tmp_path, config)
        assert (tmp_path / "docs" / "assets" / "logo.svg").read_text() == "<svg>test</svg>"
        assert (tmp_path / "docs" / "assets" / "logo-white.svg").read_text() == "<svg>white</svg>"

    def test_noop_when_no_packaged_logo(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        config = ProjectConfig()
        with patch("speks.web.builder._get_packaged_asset", return_value=None):
            _copy_logo_if_present(tmp_path, config)
        assert not (tmp_path / "docs" / "assets").exists()


class TestBuildSite:
    def test_produces_output(self, project: Path) -> None:
        out = build_site(project)
        assert out.is_dir()
        assert (out / "index.html").exists()

    def test_page_contains_code(self, project: Path) -> None:
        out = build_site(project)
        intro = (out / "intro" / "index.html").read_text(encoding="utf-8")
        assert "def evaluer" in intro

    def test_page_contains_playground(self, project: Path) -> None:
        out = build_site(project)
        intro = (out / "intro" / "index.html").read_text(encoding="utf-8")
        assert "speks-playground-widget" in intro
        assert "Run rule" in intro

    def test_playground_js_injected(self, project: Path) -> None:
        out = build_site(project)
        intro = (out / "intro" / "index.html").read_text(encoding="utf-8")
        assert "swRunFunction" in intro

    def test_manifest_written(self, project: Path) -> None:
        out = build_site(project)
        assert (out / "playground_manifest.json").exists()

    def test_material_theme_assets(self, project: Path) -> None:
        out = build_site(project)
        # mkdocs-material generates assets/ with stylesheets
        assert (out / "assets").is_dir()

    def test_search_index(self, project: Path) -> None:
        out = build_site(project)
        assert (out / "search" / "search_index.json").exists()
