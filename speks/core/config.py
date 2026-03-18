"""Load and validate ``speks.toml`` project configuration."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 12):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[import-not-found,unused-ignore]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef,import-not-found,unused-ignore]


@dataclass
class ProjectConfig:
    """Parsed speks.toml."""

    project_name: str = "My Project"
    src_dir: str = "src"
    docs_dir: str = "docs"
    diagrams_dir: str = "diagrams"
    output_dir: str = "site"
    theme_color: str = "#1976D2"
    serve_port: int = 8000
    locale: str = "en"
    testcases_dir: str = "testcases"
    run_timeout: int = 10
    plantuml_server: str = "https://www.plantuml.com/plantuml"
    git_revisions: int = 3


def load_config(project_root: Path) -> ProjectConfig:
    """Read ``speks.toml`` from *project_root* and return a config."""
    toml_path = project_root / "speks.toml"
    if not toml_path.exists():
        return ProjectConfig()

    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)

    proj = raw.get("project", {})
    return ProjectConfig(
        project_name=proj.get("name", ProjectConfig.project_name),
        src_dir=proj.get("src_dir", ProjectConfig.src_dir),
        docs_dir=proj.get("docs_dir", ProjectConfig.docs_dir),
        diagrams_dir=proj.get("diagrams_dir", ProjectConfig.diagrams_dir),
        output_dir=proj.get("output_dir", ProjectConfig.output_dir),
        theme_color=proj.get("theme_color", ProjectConfig.theme_color),
        serve_port=proj.get("serve_port", ProjectConfig.serve_port),
        locale=proj.get("locale", ProjectConfig.locale),
        testcases_dir=proj.get("testcases_dir", ProjectConfig.testcases_dir),
        run_timeout=proj.get("run_timeout", ProjectConfig.run_timeout),
        plantuml_server=proj.get("plantuml_server", ProjectConfig.plantuml_server),
        git_revisions=proj.get("git_revisions", ProjectConfig.git_revisions),
    )
