"""Markdown parser with custom Speks tags.

Supported tags
--------------
``@[code](path/to/file.py:symbol_name)``
    Extracts the named function or class from the Python file and injects it
    as a fenced code block.  If *symbol_name* is omitted the whole file is
    included.

``@[plantuml](path/to/diagram.puml)``
    Reads the PlantUML source and wraps it in a fenced block marked for later
    SVG conversion.

``@[playground](path/to/file.py:function_name)``
    Generates an interactive playground widget placeholder that the web
    builder will turn into a live form.

``@[contract](path/to/file.py:function_name)``
    Generates a Markdown table of the function's inputs and outputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from speks.core.code_extractor import extract_function, parse_tag_arg
from speks.core.tag_resolvers import (
    TAG_RE,
    resolve_code,
    resolve_contract,
    resolve_mermaid,
    resolve_plantuml,
)


@dataclass
class ParsedPage:
    """Result of parsing a single Markdown file."""

    source_path: Path
    raw_markdown: str
    resolved_markdown: str = ""
    playgrounds: list[PlaygroundSpec] = field(default_factory=list)


@dataclass
class PlaygroundSpec:
    """Describes one interactive playground widget."""

    function_name: str
    source_path: Path
    parameters: list[dict[str, str | None]]
    return_annotation: str | None
    source_code: str
    docstring: str | None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_markdown(md_path: Path, project_root: Path) -> ParsedPage:
    """Parse a Markdown file, resolving all Speks custom tags.

    Parameters
    ----------
    md_path:
        Absolute or relative path to the ``.md`` file.
    project_root:
        The root of the analyst's workspace (where ``speks.toml`` lives).
        Tag arguments are resolved relative to this root.
    """
    raw = md_path.read_text(encoding="utf-8")
    page = ParsedPage(source_path=md_path, raw_markdown=raw)

    def _replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        arg = match.group("arg")

        if kind == "code":
            return resolve_code(arg, project_root)
        elif kind == "plantuml":
            return resolve_plantuml(arg, project_root, mode="markdown")
        elif kind == "mermaid":
            return resolve_mermaid(arg, project_root)
        elif kind == "playground":
            return _resolve_playground_with_spec(arg, project_root, page)
        elif kind == "contract":
            return resolve_contract(arg, project_root, mode="markdown")
        return match.group(0)  # fallback — keep original

    page.resolved_markdown = TAG_RE.sub(_replace, raw)
    return page


# ---------------------------------------------------------------------------
# Playground — parser-specific (collects PlaygroundSpec)
# ---------------------------------------------------------------------------


def _resolve_playground_with_spec(arg: str, root: Path, page: ParsedPage) -> str:
    """Resolve playground tag, collecting metadata into *page.playgrounds*."""
    file_part, class_name, func_name = parse_tag_arg(arg)
    if not func_name:
        return "<!-- speks: playground tag requires file:function format -->"

    file_path = root / file_part

    if not file_path.exists():
        return f"<!-- speks: file not found: {file_part} -->"

    try:
        info = extract_function(file_path, func_name, class_name=class_name)
    except ValueError:
        label = f"{class_name}:{func_name}" if class_name else func_name
        return f"<!-- speks: function '{label}' not found in {file_part} -->"

    qualified_name = f"{class_name}.{func_name}" if class_name else func_name
    spec = PlaygroundSpec(
        function_name=qualified_name,
        source_path=file_path,
        parameters=[
            {"name": p.name, "annotation": p.annotation, "default": p.default}
            for p in info.parameters
        ],
        return_annotation=info.return_annotation,
        source_code=info.source,
        docstring=info.docstring,
    )
    page.playgrounds.append(spec)

    # Emit a placeholder <div> that the site builder will hydrate.
    return f'<div class="speks-playground" data-function="{qualified_name}" data-source="{file_part}"></div>'
