"""Tests for speks.core.git — git utilities for multi-version builds."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from speks.core.git import (
    RevisionInfo,
    extract_project_at_revision,
    get_file_at_revision,
    get_recent_revisions,
    get_repo_root,
    is_git_repo,
)


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository with a few commits."""
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

    # Commit 1 — initial
    (repo / "docs").mkdir()
    (repo / "docs" / "index.md").write_text("# Welcome\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "rules.py").write_text("def f(): return 1\n", encoding="utf-8")
    _run("add", ".")
    _run("commit", "-m", "Initial commit")

    # Commit 2 — update docs
    (repo / "docs" / "index.md").write_text(
        "# Welcome\n\nUpdated content.\n", encoding="utf-8",
    )
    _run("add", ".")
    _run("commit", "-m", "Update docs")

    # Commit 3 — add page
    (repo / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    _run("add", ".")
    _run("commit", "-m", "Add guide page")

    return repo


class TestIsGitRepo:
    def test_true_for_git_repo(self, git_repo: Path) -> None:
        assert is_git_repo(git_repo) is True

    def test_false_for_non_repo(self, tmp_path: Path) -> None:
        assert is_git_repo(tmp_path) is False

    def test_false_for_nonexistent(self, tmp_path: Path) -> None:
        assert is_git_repo(tmp_path / "nope") is False


class TestGetRepoRoot:
    def test_returns_repo_root(self, git_repo: Path) -> None:
        root = get_repo_root(git_repo)
        assert root is not None
        assert root == git_repo

    def test_returns_root_from_subdirectory(self, git_repo: Path) -> None:
        root = get_repo_root(git_repo / "docs")
        assert root is not None
        assert root == git_repo

    def test_returns_none_for_non_repo(self, tmp_path: Path) -> None:
        assert get_repo_root(tmp_path) is None


class TestGetRecentRevisions:
    def test_returns_revisions(self, git_repo: Path) -> None:
        revs = get_recent_revisions(git_repo, count=3)
        assert len(revs) == 3
        assert all(isinstance(r, RevisionInfo) for r in revs)

    def test_newest_first(self, git_repo: Path) -> None:
        revs = get_recent_revisions(git_repo, count=3)
        assert revs[0].subject == "Add guide page"
        assert revs[1].subject == "Update docs"
        assert revs[2].subject == "Initial commit"

    def test_count_limits_results(self, git_repo: Path) -> None:
        revs = get_recent_revisions(git_repo, count=1)
        assert len(revs) == 1
        assert revs[0].subject == "Add guide page"

    def test_short_sha_populated(self, git_repo: Path) -> None:
        revs = get_recent_revisions(git_repo, count=1)
        assert len(revs[0].short_sha) >= 7
        assert revs[0].sha.startswith(revs[0].short_sha)

    def test_empty_for_non_repo(self, tmp_path: Path) -> None:
        assert get_recent_revisions(tmp_path) == []


class TestGetFileAtRevision:
    def test_reads_current_file(self, git_repo: Path) -> None:
        revs = get_recent_revisions(git_repo, count=1)
        content = get_file_at_revision(git_repo, revs[0].sha, "docs/index.md")
        assert content is not None
        assert "Updated content" in content

    def test_reads_old_revision(self, git_repo: Path) -> None:
        revs = get_recent_revisions(git_repo, count=3)
        # The initial commit should have the original content
        content = get_file_at_revision(
            git_repo, revs[2].sha, "docs/index.md",
        )
        assert content is not None
        assert "Updated content" not in content
        assert "# Welcome" in content

    def test_returns_none_for_missing_file(self, git_repo: Path) -> None:
        revs = get_recent_revisions(git_repo, count=3)
        # guide.md didn't exist in the initial commit
        content = get_file_at_revision(
            git_repo, revs[2].sha, "docs/guide.md",
        )
        assert content is None

    def test_returns_none_for_bad_revision(self, git_repo: Path) -> None:
        content = get_file_at_revision(
            git_repo, "0000000000000000000000000000000000000000", "docs/index.md",
        )
        assert content is None


class TestExtractProjectAtRevision:
    def test_extracts_files(self, git_repo: Path, tmp_path: Path) -> None:
        revs = get_recent_revisions(git_repo, count=1)
        target = tmp_path / "extracted"
        ok = extract_project_at_revision(git_repo, revs[0].sha, target)
        assert ok is True
        assert (target / "docs" / "index.md").is_file()
        assert (target / "docs" / "guide.md").is_file()
        assert (target / "src" / "rules.py").is_file()

    def test_old_revision_lacks_new_files(
        self, git_repo: Path, tmp_path: Path,
    ) -> None:
        revs = get_recent_revisions(git_repo, count=3)
        target = tmp_path / "old"
        ok = extract_project_at_revision(git_repo, revs[2].sha, target)
        assert ok is True
        assert (target / "docs" / "index.md").is_file()
        # guide.md was only added in commit 3
        assert not (target / "docs" / "guide.md").exists()

    def test_returns_false_for_bad_revision(
        self, git_repo: Path, tmp_path: Path,
    ) -> None:
        target = tmp_path / "bad"
        ok = extract_project_at_revision(git_repo, "invalid_sha", target)
        assert ok is False


# ---------------------------------------------------------------------------
# Subdirectory-of-repo scenario (project is not at the git root)
# ---------------------------------------------------------------------------


@pytest.fixture()
def git_repo_with_subproject(tmp_path: Path) -> tuple[Path, Path]:
    """Git repo where the speks project lives in a subdirectory."""
    repo = tmp_path / "monorepo"
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

    # Project lives under projects/my-analysis/
    project = repo / "projects" / "my-analysis"
    (project / "docs").mkdir(parents=True)
    (project / "src").mkdir(parents=True)
    (project / "docs" / "index.md").write_text(
        "# Hello v1\n", encoding="utf-8",
    )
    (project / "src" / "rules.py").write_text(
        "def f(): return 1\n", encoding="utf-8",
    )

    # Also a file at repo root (unrelated)
    (repo / "README.md").write_text("# Monorepo\n", encoding="utf-8")

    _run("add", ".")
    _run("commit", "-m", "Initial")

    # Second commit — update docs in the subproject
    (project / "docs" / "index.md").write_text(
        "# Hello v2\n\nUpdated.\n", encoding="utf-8",
    )
    _run("add", ".")
    _run("commit", "-m", "Update subproject docs")

    return repo, project


class TestSubdirectoryProject:
    def test_get_file_at_revision_from_subdir(
        self, git_repo_with_subproject: tuple[Path, Path],
    ) -> None:
        _repo, project = git_repo_with_subproject
        revs = get_recent_revisions(project, count=2)
        # Newest commit updated index.md
        content = get_file_at_revision(project, revs[0].sha, "docs/index.md")
        assert content is not None
        assert "v2" in content

        # Oldest commit had v1
        content = get_file_at_revision(project, revs[1].sha, "docs/index.md")
        assert content is not None
        assert "v1" in content
        assert "Updated" not in content

    def test_revisions_scoped_to_subdir(
        self, git_repo_with_subproject: tuple[Path, Path],
    ) -> None:
        _repo, project = git_repo_with_subproject
        revs = get_recent_revisions(project, count=10)
        # Both commits touched the subproject
        assert len(revs) == 2

    def test_extract_at_revision_from_subdir(
        self, git_repo_with_subproject: tuple[Path, Path], tmp_path: Path,
    ) -> None:
        _repo, project = git_repo_with_subproject
        revs = get_recent_revisions(project, count=1)
        target = tmp_path / "extracted"
        ok = extract_project_at_revision(project, revs[0].sha, target)
        assert ok is True
        assert (target / "docs" / "index.md").is_file()
        # Should NOT contain the repo root README
        assert not (target / "README.md").exists()
