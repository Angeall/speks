"""MkDocs plugin that renders sequence diagrams from Python source.

Supported tags
--------------
``@[sequence](src/regles.py:evaluer_credit_avance)``
    Analyze the function body and render a Mermaid sequence diagram
    showing service calls, function calls, and conditional branches.

The generated diagrams use Mermaid ``sequenceDiagram`` syntax with
``opt`` / ``alt`` fragments for conditional blocks.
"""

from __future__ import annotations

import re
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from speks.core.sequence_analyzer import generate_sequence_diagram
from speks.i18n import t

_SEQ_TAG_RE = re.compile(r"@\[sequence\]\((?P<arg>[^)]+)\)")


class SpeksSequencePlugin(BasePlugin):  # type: ignore[type-arg,no-untyped-call]
    """Resolve ``@[sequence]`` tags into Mermaid sequence diagrams."""

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
            return _resolve_sequence(match.group("arg"), root)

        return _SEQ_TAG_RE.sub(_replace, markdown)


def _resolve_sequence(arg: str, root: Path) -> str:
    """Turn ``@[sequence](...)`` into a Mermaid code block."""
    from speks.core.code_extractor import parse_tag_arg

    file_part, class_name, func_name = parse_tag_arg(arg)
    if not func_name:
        return "<!-- speks-sequence: expected format file.py:function_name -->"

    # For class methods, use Class.method as the lookup key
    if class_name:
        func_name = f"{class_name}.{func_name}"

    dir_part = file_part
    src_path = root / dir_part

    if not src_path.exists():
        return f"<!-- speks-sequence: path not found: {dir_part} -->"

    if src_path.is_file():
        analyze_dir = src_path.parent
    else:
        analyze_dir = src_path

    mermaid = generate_sequence_diagram(func_name, analyze_dir, root)

    if mermaid is None:
        return f"<!-- speks-sequence: function '{func_name}' not found or has no calls -->"

    title = t("sequence.title")
    return f"""!!! example "{title} — {func_name}"

```mermaid
{mermaid}
```
"""
