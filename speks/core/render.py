"""Render a Markdown file with Speks tags to standalone HTML.

Resolves all custom tags via :mod:`speks.core.tag_resolvers`, converts
the Markdown to HTML via the ``markdown`` library and wraps the result
in a self-contained HTML page with embedded CSS.
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown  # type: ignore[import-untyped]

from speks.core.styles import (
    DIAGRAM_PLACEHOLDER_CSS,
    STANDALONE_BASE_CSS,
    STANDALONE_OVERRIDES_CSS,
    WIDGET_CSS,
)
from speks.core.tag_resolvers import (
    TAG_RE,
    resolve_code,
    resolve_contract,
    resolve_mermaid,
    resolve_plantuml,
    resolve_playground,
)

# ---------------------------------------------------------------------------
# Embedded CSS — assembled from shared styles + standalone extras
# ---------------------------------------------------------------------------

_STANDALONE_CSS = (
    STANDALONE_BASE_CSS
    + WIDGET_CSS
    + STANDALONE_OVERRIDES_CSS
    + DIAGRAM_PLACEHOLDER_CSS
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_tags(md_text: str, project_root: Path) -> str:
    """Resolve all ``@[kind](arg)`` tags in *md_text* for standalone output."""

    def _replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        arg = match.group("arg")
        if kind == "code":
            return resolve_code(arg, project_root)
        elif kind == "plantuml":
            return resolve_plantuml(arg, project_root, mode="standalone")
        elif kind == "mermaid":
            return resolve_mermaid(arg, project_root)
        elif kind == "playground":
            return resolve_playground(arg, project_root, mode="standalone")
        elif kind == "contract":
            return resolve_contract(arg, project_root, mode="standalone")
        return match.group(0)

    return TAG_RE.sub(_replace, md_text)


def render_markdown_to_html(md_path: Path, project_root: Path) -> str:
    """Read a Markdown file, resolve Speks tags, and return standalone HTML."""
    raw = md_path.read_text(encoding="utf-8")
    resolved = resolve_tags(raw, project_root)

    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc", "codehilite"],
        extension_configs={"codehilite": {"guess_lang": False}},
    )
    body = md.convert(resolved)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="fr">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{md_path.stem}</title>\n"
        f"  <style>{_STANDALONE_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )
