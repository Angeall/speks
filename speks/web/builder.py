"""Site builder — delegates to MkDocs with mkdocs-material theme.

Also generates a ``mkdocs.yml`` on the fly if one does not exist, and writes
the playground manifest used by the FastAPI server.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
import shutil
import tempfile
from pathlib import Path

from speks.core.config import ProjectConfig, load_config
from speks.core.parser import parse_markdown

logger = logging.getLogger(__name__)


def build_site(
    project_root: Path,
    *,
    revisions_override: int | None = None,
) -> Path:
    """Build the site via MkDocs and return the output directory.

    When the project is inside a git repository and *git_revisions* > 0,
    historical versions are also built into ``_versions/<sha>/``.
    """
    config = load_config(project_root)

    # Copy logo into docs/assets/ so MkDocs can pick it up
    _copy_logo_if_present(project_root, config)

    _ensure_mkdocs_yml(project_root, config)

    output_dir = project_root / config.output_dir

    # Run MkDocs build programmatically
    from mkdocs.commands.build import build as mkdocs_build
    from mkdocs.config import load_config as load_mkdocs_config

    mkdocs_cfg = load_mkdocs_config(str(project_root / "mkdocs.yml"))
    mkdocs_build(mkdocs_cfg)

    # Write playground manifest for the API server
    _write_playground_manifest(project_root, config, output_dir)

    # Build historical versions if git is available
    num_revisions = revisions_override if revisions_override is not None else config.git_revisions
    versions = _build_versioned_sites(project_root, config, output_dir, num_revisions)

    # Write versions manifest
    _write_versions_manifest(output_dir, versions)

    return output_dir


# ---------------------------------------------------------------------------
# Versioned builds
# ---------------------------------------------------------------------------


def _build_versioned_sites(
    project_root: Path,
    config: ProjectConfig,
    output_dir: Path,
    num_revisions: int,
) -> list[dict[str, str]]:
    """Build the site for each recent git revision.

    Returns a list of version metadata dicts (empty if not a git repo or no
    revisions found).
    """
    if num_revisions <= 0:
        return []

    from speks.core.git import (
        extract_project_at_revision,
        get_recent_revisions,
        is_git_repo,
    )

    if not is_git_repo(project_root):
        return []

    revisions = get_recent_revisions(project_root, count=num_revisions)
    if not revisions:
        return []

    versions: list[dict[str, str]] = []
    versions_dir = output_dir / "_versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    for rev in revisions:
        version_output = versions_dir / rev.short_sha
        if version_output.exists():
            # Already built (e.g. incremental)
            versions.append({
                "sha": rev.sha,
                "short_sha": rev.short_sha,
                "subject": rev.subject,
                "author": rev.author,
                "date": rev.date,
            })
            continue

        logger.info("Building version %s (%s)…", rev.short_sha, rev.subject)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if not extract_project_at_revision(project_root, rev.sha, tmp_path):
                logger.warning("Failed to extract revision %s", rev.short_sha)
                continue

            # Try to build in the temp directory
            try:
                _build_single_version(tmp_path, config, version_output)
                versions.append({
                    "sha": rev.sha,
                    "short_sha": rev.short_sha,
                    "subject": rev.subject,
                    "author": rev.author,
                    "date": rev.date,
                })
            except Exception:
                logger.warning(
                    "Failed to build revision %s", rev.short_sha, exc_info=True,
                )

    return versions


def _build_single_version(
    project_dir: Path,
    parent_config: ProjectConfig,
    output_dir: Path,
) -> None:
    """Build a single historical version into *output_dir*.

    Playgrounds are rendered in read-only (standalone) mode so that
    they don't attempt to execute code from an old revision.
    """
    import os

    from mkdocs.commands.build import build as mkdocs_build
    from mkdocs.config import load_config as load_mkdocs_config

    # Load config from the historical version (or use parent defaults)
    try:
        rev_config = load_config(project_dir)
    except Exception:
        rev_config = parent_config

    _copy_logo_if_present(project_dir, rev_config)
    _ensure_mkdocs_yml(project_dir, rev_config)

    # Override the output directory to our versioned path
    mkdocs_yml = project_dir / "mkdocs.yml"
    content = mkdocs_yml.read_text(encoding="utf-8")

    # Replace site_dir in the yml to point to our output.
    # Use line-by-line replacement instead of re.sub to avoid issues
    # with backslashes in Windows paths being interpreted as escapes.
    new_lines = []
    for line in content.splitlines(keepends=True):
        if line.strip().startswith("site_dir:"):
            # Use forward slashes so YAML doesn't interpret
            # backslashes as escape sequences on Windows.
            safe_path = str(output_dir).replace("\\", "/")
            new_lines.append(f'site_dir: "{safe_path}"\n')
        else:
            new_lines.append(line)
    mkdocs_yml.write_text("".join(new_lines), encoding="utf-8")

    mkdocs_cfg = load_mkdocs_config(str(mkdocs_yml))

    # Signal to the tags plugin that playgrounds should be read-only
    os.environ["SPEKS_VERSIONED_BUILD"] = "1"
    try:
        mkdocs_build(mkdocs_cfg)
    finally:
        os.environ.pop("SPEKS_VERSIONED_BUILD", None)


def _write_versions_manifest(
    output_dir: Path,
    versions: list[dict[str, str]],
) -> None:
    """Write ``versions.json`` into the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "versions.json").write_text(
        json.dumps(versions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_packaged_asset(name: str) -> Path | None:
    """Return the path to an asset bundled inside the speks package."""
    ref = importlib.resources.files("speks").joinpath("assets", name)
    asset_path = Path(str(ref))
    if asset_path.is_file():
        return asset_path
    return None


def _copy_logo_if_present(project_root: Path, config: ProjectConfig) -> None:
    """Copy the packaged logos into the project's docs/assets/."""
    assets_dir = project_root / config.docs_dir / "assets"
    for name in ("logo.svg", "logo-white.svg"):
        src = _get_packaged_asset(name)
        if src is not None:
            assets_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, assets_dir / name)


def _ensure_mkdocs_yml(project_root: Path, config: ProjectConfig) -> None:
    """Generate ``mkdocs.yml`` if it doesn't already exist."""
    yml_path = project_root / "mkdocs.yml"
    if yml_path.exists():
        return

    logo_line = ""
    if _get_packaged_asset("logo-white.svg") is not None:
        logo_line = "  logo: assets/logo-white.svg\n  favicon: assets/logo.svg\n"

    yml = f"""\
site_name: "{config.project_name}"
docs_dir: "{config.docs_dir}"
site_dir: "{config.output_dir}"

theme:
  name: material
{logo_line}\
  palette:
    primary: custom
  features:
    - navigation.instant
    - navigation.sections
    - navigation.top
    - search.suggest
    - content.code.copy

plugins:
  - search
  - speks-tags
  - speks-playground
  - speks-dependencies
  - speks-plantuml:
      server: "{config.plantuml_server}"
  - speks-sequence
  - speks-versioning

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
        - name: plantuml
          class: plantuml
          format: !!python/name:pymdownx.superfences.fence_code_format
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.tabbed:
      alternate_style: true
  - tables
  - toc:
      permalink: true
"""
    yml_path.write_text(yml, encoding="utf-8")


def _write_playground_manifest(
    project_root: Path,
    config: ProjectConfig,
    output_dir: Path,
) -> None:
    """Write a JSON manifest listing all playground functions."""
    docs_dir = project_root / config.docs_dir
    md_files = sorted(docs_dir.glob("**/*.md"))

    manifest: list[dict[str, object]] = []
    for md_file in md_files:
        parsed = parse_markdown(md_file, project_root)
        for pg in parsed.playgrounds:
            manifest.append({
                "function": pg.function_name,
                "source_file": str(pg.source_path.relative_to(project_root)),
                "parameters": pg.parameters,
                "return_annotation": pg.return_annotation,
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "playground_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
