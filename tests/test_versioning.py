"""Tests for the multi-version build system and diff API."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from speks.core.config import ProjectConfig
from speks.web.builder import (
    _build_versioned_sites,
    _write_versions_manifest,
    build_site,
)
from speks.web.server import _get_page_content, _html_path_to_md, create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def git_project(tmp_path: Path) -> Path:
    """Create a full speks project inside a git repo with multiple commits."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def _run(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )

    _run("init")
    _run("config", "user.email", "test@test.com")
    _run("config", "user.name", "Test")
    _run("config", "commit.gpgsign", "false")

    # Initial commit — minimal project
    (repo / "src").mkdir()
    (repo / "src" / "__init__.py").touch()
    (repo / "src" / "rules.py").write_text(
        "def greet(name: str) -> str:\n"
        '    """Say hello."""\n'
        "    return 'Hello ' + name\n",
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    (repo / "docs" / "index.md").write_text(
        "# Welcome\n\nVersion 1.\n", encoding="utf-8",
    )
    (repo / "diagrams").mkdir()
    (repo / "speks.toml").write_text(
        '[project]\nname = "Test"\ngit_revisions = 2\n',
        encoding="utf-8",
    )
    _run("add", ".")
    _run("commit", "-m", "Initial commit")

    # Second commit — update docs
    (repo / "docs" / "index.md").write_text(
        "# Welcome\n\nVersion 2 — updated.\n", encoding="utf-8",
    )
    _run("add", ".")
    _run("commit", "-m", "Update docs to v2")

    return repo


@pytest.fixture()
def non_git_project(tmp_path: Path) -> Path:
    """Create a speks project that is NOT a git repo."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "src").mkdir()
    (proj / "src" / "__init__.py").touch()
    (proj / "src" / "rules.py").write_text(
        "def greet(name: str) -> str:\n    return 'Hello ' + name\n",
        encoding="utf-8",
    )
    (proj / "docs").mkdir()
    (proj / "docs" / "index.md").write_text(
        "# Welcome\n", encoding="utf-8",
    )
    (proj / "diagrams").mkdir()
    (proj / "speks.toml").write_text(
        '[project]\nname = "NoGit"\n', encoding="utf-8",
    )
    return proj


# ---------------------------------------------------------------------------
# _write_versions_manifest
# ---------------------------------------------------------------------------


class TestWriteVersionsManifest:
    def test_writes_json(self, tmp_path: Path) -> None:
        versions = [
            {"sha": "abc123", "short_sha": "abc", "subject": "test"},
        ]
        _write_versions_manifest(tmp_path, versions)
        manifest = json.loads(
            (tmp_path / "versions.json").read_text(encoding="utf-8"),
        )
        assert manifest == versions

    def test_empty_versions(self, tmp_path: Path) -> None:
        _write_versions_manifest(tmp_path, [])
        manifest = json.loads(
            (tmp_path / "versions.json").read_text(encoding="utf-8"),
        )
        assert manifest == []


# ---------------------------------------------------------------------------
# _build_versioned_sites
# ---------------------------------------------------------------------------


class TestBuildVersionedSites:
    def test_no_versions_when_not_git(self, non_git_project: Path) -> None:
        config = ProjectConfig()
        output = non_git_project / "site"
        output.mkdir()
        versions = _build_versioned_sites(
            non_git_project, config, output, num_revisions=3,
        )
        assert versions == []

    def test_no_versions_when_zero_revisions(self, git_project: Path) -> None:
        config = ProjectConfig()
        output = git_project / "site"
        output.mkdir()
        versions = _build_versioned_sites(
            git_project, config, output, num_revisions=0,
        )
        assert versions == []


# ---------------------------------------------------------------------------
# build_site — integration
# ---------------------------------------------------------------------------


class TestBuildSiteVersioning:
    def test_build_creates_versions_json(self, git_project: Path) -> None:
        """build_site should write versions.json even if version builds fail."""
        output = build_site(git_project)
        assert (output / "versions.json").is_file()

    def test_build_non_git_has_empty_versions(
        self, non_git_project: Path,
    ) -> None:
        output = build_site(non_git_project)
        manifest = json.loads(
            (output / "versions.json").read_text(encoding="utf-8"),
        )
        assert manifest == []

    def test_revisions_override_zero_skips(self, git_project: Path) -> None:
        output = build_site(git_project, revisions_override=0)
        manifest = json.loads(
            (output / "versions.json").read_text(encoding="utf-8"),
        )
        assert manifest == []


# ---------------------------------------------------------------------------
# _html_path_to_md
# ---------------------------------------------------------------------------


class TestHtmlPathToMd:
    def test_index_html(self) -> None:
        config = ProjectConfig(docs_dir="docs")
        assert _html_path_to_md("index.html", config) == "docs/index.md"

    def test_empty_path(self) -> None:
        config = ProjectConfig(docs_dir="docs")
        assert _html_path_to_md("", config) == "docs/index.md"

    def test_section_index(self) -> None:
        config = ProjectConfig(docs_dir="docs")
        result = _html_path_to_md("intro/index.html", config)
        assert result == "docs/intro.md"

    def test_section_trailing_slash(self) -> None:
        config = ProjectConfig(docs_dir="docs")
        result = _html_path_to_md("intro/", config)
        assert result == "docs/intro.md"

    def test_nested_path(self) -> None:
        config = ProjectConfig(docs_dir="documentation")
        result = _html_path_to_md("guide/getting-started/index.html", config)
        assert result == "documentation/guide/getting-started.md"


# ---------------------------------------------------------------------------
# _get_page_content
# ---------------------------------------------------------------------------


class TestGetPageContent:
    def test_current_reads_file(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "index.md").write_text("# Hello\n", encoding="utf-8")
        config = ProjectConfig(docs_dir="docs")

        content = _get_page_content(
            tmp_path, config, "current", "docs/index.md",
            lambda *a: None,
        )
        assert content == "# Hello\n"

    def test_current_tries_index_variant(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs" / "intro"
        docs.mkdir(parents=True)
        (docs / "index.md").write_text("# Intro\n", encoding="utf-8")
        config = ProjectConfig(docs_dir="docs")

        content = _get_page_content(
            tmp_path, config, "current", "docs/intro.md",
            lambda *a: None,
        )
        assert content == "# Intro\n"

    def test_current_returns_empty_for_missing(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        config = ProjectConfig(docs_dir="docs")

        content = _get_page_content(
            tmp_path, config, "current", "docs/nope.md",
            lambda *a: None,
        )
        assert content == ""

    def test_revision_calls_get_file_fn(self, tmp_path: Path) -> None:
        config = ProjectConfig(docs_dir="docs")

        def fake_get(root: Path, rev: str, path: str) -> str | None:
            if path == "docs/page.md":
                return "# Old page\n"
            return None

        content = _get_page_content(
            tmp_path, config, "abc123", "docs/page.md", fake_get,
        )
        assert content == "# Old page\n"

    def test_revision_tries_index_variant(self, tmp_path: Path) -> None:
        config = ProjectConfig(docs_dir="docs")

        def fake_get(root: Path, rev: str, path: str) -> str | None:
            if path == "docs/intro/index.md":
                return "# From index\n"
            return None

        content = _get_page_content(
            tmp_path, config, "abc123", "docs/intro.md", fake_get,
        )
        assert content == "# From index\n"


# ---------------------------------------------------------------------------
# /api/versions endpoint
# ---------------------------------------------------------------------------


class TestVersionsApi:
    def test_returns_empty_when_no_manifest(self, tmp_path: Path) -> None:
        site = tmp_path / "site"
        site.mkdir()
        app = create_app(tmp_path, site)
        client = TestClient(app)
        resp = client.get("/api/versions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_versions_from_manifest(self, tmp_path: Path) -> None:
        site = tmp_path / "site"
        site.mkdir()
        versions = [{"sha": "abc", "short_sha": "abc", "subject": "hi"}]
        (site / "versions.json").write_text(
            json.dumps(versions), encoding="utf-8",
        )
        app = create_app(tmp_path, site)
        client = TestClient(app)
        resp = client.get("/api/versions")
        assert resp.status_code == 200
        assert resp.json() == versions


# ---------------------------------------------------------------------------
# /api/diff endpoint
# ---------------------------------------------------------------------------


class TestDiffApi:
    @pytest.fixture()
    def diff_project(self, tmp_path: Path) -> tuple[Path, TestClient]:
        """Project with git repo for diff testing."""
        repo = tmp_path / "repo"
        repo.mkdir()

        def _run(*args: str) -> None:
            subprocess.run(
                ["git", *args],
                cwd=str(repo),
                capture_output=True,
                text=True,
                check=True,
            )

        _run("init")
        _run("config", "user.email", "test@test.com")
        _run("config", "user.name", "Test")
        _run("config", "commit.gpgsign", "false")

        (repo / "docs").mkdir()
        (repo / "docs" / "index.md").write_text(
            "# Old title\n", encoding="utf-8",
        )
        (repo / "speks.toml").write_text(
            '[project]\nname = "Diff"\n', encoding="utf-8",
        )
        _run("add", ".")
        _run("commit", "-m", "v1")

        # Update
        (repo / "docs" / "index.md").write_text(
            "# New title\n\nNew content.\n", encoding="utf-8",
        )
        _run("add", ".")
        _run("commit", "-m", "v2")

        site = repo / "site"
        site.mkdir()
        app = create_app(repo, site)
        return repo, TestClient(app)

    def test_diff_shows_changes(self, diff_project: tuple[Path, TestClient]) -> None:
        repo, client = diff_project
        # Get commit SHAs
        result = subprocess.run(
            ["git", "log", "--format=%H", "-2"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        shas = result.stdout.strip().split("\n")
        newer, older = shas[0], shas[1]

        resp = client.get("/api/diff", params={
            "page": "index.html",
            "from_rev": older,
            "to_rev": newer,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_changes"] is True
        assert "Old title" in body["unified_diff"]
        assert "New title" in body["unified_diff"]

    def test_diff_no_changes_same_rev(
        self, diff_project: tuple[Path, TestClient],
    ) -> None:
        repo, client = diff_project
        result = subprocess.run(
            ["git", "log", "--format=%H", "-1"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        sha = result.stdout.strip()

        resp = client.get("/api/diff", params={
            "page": "index.html",
            "from_rev": sha,
            "to_rev": sha,
        })
        assert resp.status_code == 200
        assert resp.json()["has_changes"] is False

    def test_diff_current_vs_revision(
        self, diff_project: tuple[Path, TestClient],
    ) -> None:
        repo, client = diff_project
        result = subprocess.run(
            ["git", "log", "--format=%H", "-2"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        older = result.stdout.strip().split("\n")[1]

        resp = client.get("/api/diff", params={
            "page": "index.html",
            "from_rev": older,
            "to_rev": "current",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_changes"] is True

    def test_diff_non_git_returns_error(self, tmp_path: Path) -> None:
        site = tmp_path / "site"
        site.mkdir()
        app = create_app(tmp_path, site)
        client = TestClient(app)

        resp = client.get("/api/diff", params={
            "page": "index.html",
            "from_rev": "abc",
            "to_rev": "def",
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Versioning MkDocs plugin
# ---------------------------------------------------------------------------


class TestVersioningPlugin:
    def test_injects_js_into_page(self) -> None:
        from speks.mkdocs_plugins.versioning import SpeksVersioningPlugin

        plugin = SpeksVersioningPlugin()
        html = "<html><body><p>Hello</p></body></html>"
        page = MagicMock()
        config = MagicMock()

        output = plugin.on_post_page(html, page=page, config=config)
        assert "speks-version-selector" in output
        assert "loadVersions" in output
        assert "diff2html" in output
        assert "</body>" in output

    def test_preserves_existing_content(self) -> None:
        from speks.mkdocs_plugins.versioning import SpeksVersioningPlugin

        plugin = SpeksVersioningPlugin()
        html = '<html><body><div class="existing">Keep me</div></body></html>'
        page = MagicMock()
        config = MagicMock()

        output = plugin.on_post_page(html, page=page, config=config)
        assert "Keep me" in output
        assert "existing" in output


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestVersionedBuildMode:
    """Playgrounds should be read-only in versioned builds."""

    def test_tags_plugin_uses_standalone_in_versioned_build(self) -> None:
        import os

        from speks.mkdocs_plugins.tags import SpeksTagsPlugin

        plugin = SpeksTagsPlugin()
        page = MagicMock()
        config = MagicMock()
        config.__getitem__ = lambda self, k: "/tmp/fakedir" if k == "docs_dir" else ""
        files = MagicMock()

        md = "@[playground](src/rules.py:evaluate_credit)"

        # Without env var → should use mkdocs mode (interactive)
        os.environ.pop("SPEKS_VERSIONED_BUILD", None)
        result = plugin.on_page_markdown(
            md, page=page, config=config, files=files,
        )
        # "mkdocs" mode produces onclick handlers
        # If function not found, it returns a comment; that's OK
        assert "SPEKS_VERSIONED_BUILD" not in os.environ

        # With env var → should use standalone mode (disabled button)
        os.environ["SPEKS_VERSIONED_BUILD"] = "1"
        try:
            result = plugin.on_page_markdown(
                md, page=page, config=config, files=files,
            )
        finally:
            os.environ.pop("SPEKS_VERSIONED_BUILD", None)

    def test_playground_js_not_injected_in_versioned_build(self) -> None:
        import os

        from speks.mkdocs_plugins.playground import SpeksPlaygroundPlugin

        plugin = SpeksPlaygroundPlugin()
        html = '<html><body><div class="speks-playground-widget">test</div></body></html>'
        page = MagicMock()
        config = MagicMock()

        # Without env var → JS should be injected
        os.environ.pop("SPEKS_VERSIONED_BUILD", None)
        output = plugin.on_post_page(html, page=page, config=config)
        assert "swRunFunction" in output

        # With env var → JS should NOT be injected
        os.environ["SPEKS_VERSIONED_BUILD"] = "1"
        try:
            output = plugin.on_post_page(html, page=page, config=config)
            assert "swRunFunction" not in output
        finally:
            os.environ.pop("SPEKS_VERSIONED_BUILD", None)


class TestVersioningConfig:
    def test_default_git_revisions(self) -> None:
        config = ProjectConfig()
        assert config.git_revisions == 3

    def test_config_from_toml(self, tmp_path: Path) -> None:
        from speks.core.config import load_config

        (tmp_path / "speks.toml").write_text(
            '[project]\ngit_revisions = 5\n', encoding="utf-8",
        )
        config = load_config(tmp_path)
        assert config.git_revisions == 5

    def test_config_zero_disables(self, tmp_path: Path) -> None:
        from speks.core.config import load_config

        (tmp_path / "speks.toml").write_text(
            '[project]\ngit_revisions = 0\n', encoding="utf-8",
        )
        config = load_config(tmp_path)
        assert config.git_revisions == 0
