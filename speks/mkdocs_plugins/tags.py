"""MkDocs plugin that resolves Speks custom tags in Markdown.

Supported tags
--------------
``@[code](path/to/file.py:symbol_name)``
    Extracts a function or class and injects it as a fenced code block.

``@[plantuml](path/to/diagram.puml)``
    Reads PlantUML source and injects it as a fenced plantuml block.

``@[mermaid](path/to/diagram.mmd)``
    Reads a Mermaid source file and injects it as a fenced mermaid block.

``@[playground](path/to/file.py:function_name)``
    Generates an interactive playground widget (HTML form) for the function.

``@[contract](path/to/file.py:function_name)``
    Displays a styled table showing function inputs (parameters with types
    and defaults) and outputs (return type).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

from speks.core.config import load_config
from speks.core.tag_resolvers import (
    TAG_RE,
    resolve_code,
    resolve_contract,
    resolve_mermaid,
    resolve_plantuml,
    resolve_playground,
)
from speks.i18n import set_locale

# Re-export resolvers so existing test imports keep working.
_resolve_code = resolve_code
_resolve_plantuml = resolve_plantuml
_resolve_mermaid = resolve_mermaid


def _resolve_playground(arg: str, root: Path) -> str:
    return resolve_playground(arg, root, mode="mkdocs")


def _resolve_contract(arg: str, root: Path) -> str:
    return resolve_contract(arg, root, mode="mkdocs")


class SpeksTagsPlugin(BasePlugin):  # type: ignore[type-arg,no-untyped-call]
    """Resolve ``@[code]``, ``@[plantuml]``, ``@[mermaid]``, ``@[playground]`` and ``@[contract]`` tags."""

    def _project_root(self, config: MkDocsConfig) -> Path:
        """Return the analyst workspace root (parent of docs_dir)."""
        return Path(config["docs_dir"]).parent

    # ----- MkDocs hook: on_page_markdown ------------------------------------

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig | None:
        """Set the i18n locale from the project configuration."""
        root = self._project_root(config)
        project_config = load_config(root)
        set_locale(project_config.locale)
        return config

    def on_page_markdown(
        self,
        markdown: str,
        *,
        page: Page,
        config: MkDocsConfig,
        files: Files,
    ) -> str:
        root = self._project_root(config)

        from speks.core.tag_resolvers import Mode

        # Historical version builds set this env var so playgrounds
        # render in read-only (standalone) mode.
        is_versioned = os.environ.get("SPEKS_VERSIONED_BUILD") == "1"
        widget_mode: Mode = "standalone" if is_versioned else "mkdocs"

        def _replace(match: re.Match[str]) -> str:
            kind = match.group("kind")
            arg = match.group("arg")

            if kind == "code":
                return resolve_code(arg, root)
            elif kind == "plantuml":
                return resolve_plantuml(arg, root, mode=widget_mode)
            elif kind == "mermaid":
                return resolve_mermaid(arg, root)
            elif kind == "playground":
                return resolve_playground(arg, root, mode=widget_mode)
            elif kind == "contract":
                return resolve_contract(arg, root, mode=widget_mode)
            return match.group(0)

        return TAG_RE.sub(_replace, markdown)
