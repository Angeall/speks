"""MkDocs plugin that renders service dependency diagrams.

Supported tags
--------------
``@[dependencies](src/)``
    Analyze all Python files under ``src/`` and render a full Mermaid
    flowchart of services and business-rule functions.

``@[dependencies](src/regles.py:evaluer_credit_avance)``
    Render only the subgraph reachable from a specific function, with
    the entry point highlighted in green.

The generated diagrams use three visual styles:

- **Green rounded box** — the entry-point function (focused mode)
- **Blue rounded box** — internal business-rule functions
- **Orange stadium** — external services (blackboxes)
"""

from __future__ import annotations

import re
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from speks.core.dependency_analyzer import analyze_directory, DependencyGraph
from speks.i18n import t

_DEP_TAG_RE = re.compile(r"@\[dependencies\]\((?P<arg>[^)]+)\)")


class SpeksDependenciesPlugin(BasePlugin):  # type: ignore[type-arg,no-untyped-call]
    """Resolve ``@[dependencies]`` tags into Mermaid diagrams."""

    def _project_root(self, config: MkDocsConfig) -> Path:
        return Path(config["docs_dir"]).parent

    def on_page_markdown(
        self,
        markdown: str,
        *,
        page: Page,
        config: MkDocsConfig,
        files: Files,
    ) -> str:
        root = self._project_root(config)

        def _replace(match: re.Match[str]) -> str:
            return _resolve_dependencies(match.group("arg"), root)

        return _DEP_TAG_RE.sub(_replace, markdown)


def _resolve_dependencies(arg: str, root: Path) -> str:
    """Turn ``@[dependencies](...)`` into a Mermaid code block."""
    # Determine if focused on a specific function
    from speks.core.code_extractor import parse_tag_arg

    highlight_func: str | None = None
    file_part, class_name, symbol = parse_tag_arg(arg)
    if symbol:
        dir_part = file_part
        highlight_func = f"{class_name}.{symbol}" if class_name else symbol
    elif class_name:
        dir_part = file_part
        highlight_func = class_name
    else:
        dir_part = file_part

    src_path = root / dir_part
    if not src_path.exists():
        return f"<!-- speks: path not found: {dir_part} -->"

    # If the path is a file, analyze its parent directory
    if src_path.is_file():
        analyze_dir = src_path.parent
    else:
        analyze_dir = src_path

    graph = analyze_directory(analyze_dir, root)

    if not graph.services and not graph.functions:
        return "<!-- speks: no services or functions found -->"

    if highlight_func and highlight_func not in graph.functions:
        return f"<!-- speks: function '{highlight_func}' not found in dependency graph -->"

    mermaid = graph.to_mermaid(highlight_func=highlight_func)

    # Build a legend block
    legend = _build_legend(highlight_func)

    return f"""{legend}

```mermaid
{mermaid}
```
"""


def _build_legend(highlight_func: str | None) -> str:
    """Return a small admonition explaining the diagram colours."""
    legend_items = []
    if highlight_func:
        legend_items.append(f":green_square: **{highlight_func}** — {t('deps.entry_point')}")
    legend_items.append(f":blue_square: {t('deps.internal_func')}")
    legend_items.append(f":orange_square: {t('deps.external_svc')}")

    body = " · ".join(legend_items)
    return f'!!! info "{t("deps.legend_title")}"\n    {body}'
