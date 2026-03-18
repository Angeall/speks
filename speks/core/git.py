"""Git utilities for multi-version documentation builds."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RevisionInfo:
    """Metadata for a single git revision."""

    sha: str
    short_sha: str
    subject: str
    author: str
    date: str  # ISO-8601


def is_git_repo(path: Path) -> bool:
    """Return ``True`` if *path* is inside a git working tree."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_recent_revisions(path: Path, count: int = 3) -> list[RevisionInfo]:
    """Return the last *count* committed revisions (newest first).

    When *path* is a subdirectory of the repository, only commits that
    touch files under that directory are returned.
    """
    fmt = "%H%n%h%n%s%n%an%n%aI"

    repo_root = get_repo_root(path)
    if repo_root is None:
        return []

    # Compute the project prefix so we only list commits relevant to it
    try:
        prefix = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return []
    prefix_posix = prefix.as_posix()

    cmd = [
        "git", "log",
        f"-{count}",
        f"--format={fmt}",
        "--",
    ]
    # Scope to the project subdirectory (or whole repo if at root)
    if prefix_posix and prefix_posix != ".":
        cmd.append(prefix_posix)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    lines = result.stdout.strip().split("\n")
    revisions: list[RevisionInfo] = []
    # Each record has 5 lines
    for i in range(0, len(lines) - 4, 5):
        revisions.append(RevisionInfo(
            sha=lines[i],
            short_sha=lines[i + 1],
            subject=lines[i + 2],
            author=lines[i + 3],
            date=lines[i + 4],
        ))
    return revisions


def extract_project_at_revision(
    project_root: Path,
    revision: str,
    target_dir: Path,
) -> bool:
    """Extract the project tree at *revision* into *target_dir*.

    Uses ``git archive`` to avoid touching the working tree.  If the
    project lives in a subdirectory of the repository only that subtree
    is extracted.  Returns ``True`` on success.
    """
    repo_root = get_repo_root(project_root)
    if repo_root is None:
        return False

    try:
        prefix = project_root.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False

    prefix_posix = prefix.as_posix()

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        # When the project is at the repo root, prefix_posix is "."
        cmd = ["git", "archive", revision]
        if prefix_posix and prefix_posix != ".":
            # Extract only the project subtree and strip the prefix
            cmd.extend([f"--prefix=", f"{prefix_posix}/"])

        archive = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            timeout=30,
        )
        if archive.returncode != 0:
            return False

        if prefix_posix and prefix_posix != ".":
            # git archive with a path spec keeps the directory prefix;
            # use tar --strip-components to remove it.
            depth = len(prefix.parts)
            extract = subprocess.run(
                ["tar", "xf", "-", f"--strip-components={depth}"],
                cwd=str(target_dir),
                input=archive.stdout,
                capture_output=True,
                timeout=30,
            )
        else:
            extract = subprocess.run(
                ["tar", "xf", "-"],
                cwd=str(target_dir),
                input=archive.stdout,
                capture_output=True,
                timeout=30,
            )
        return extract.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_file_at_revision(
    project_root: Path,
    revision: str,
    file_path: str,
) -> str | None:
    """Return the contents of *file_path* at *revision*, or ``None``.

    *file_path* is relative to *project_root* (e.g. ``docs/page.md``).
    The function accounts for the project being inside a subdirectory of
    the git repository by computing the path relative to the repo root.
    """
    repo_root = get_repo_root(project_root)
    if repo_root is None:
        return None

    # Compute the git-relative path
    try:
        prefix = project_root.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None

    git_path = (prefix / file_path).as_posix()

    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{git_path}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_repo_root(path: Path) -> Path | None:
    """Return the repository root directory, or ``None`` if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
