"""Shared CSS for Speks widgets.

Widget styles live in ``speks/assets/speks.css`` and are loaded at import
time via :mod:`importlib.resources`.  MkDocs pages consume the CSS file
through ``extra_css``; standalone rendering embeds it in a ``<style>`` tag.

Standalone-only styles (HTML reset, overrides, diagram placeholder) are
kept as Python constants since they are never served as external files.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

# ---------------------------------------------------------------------------
# Widget CSS — loaded from the packaged CSS file
# ---------------------------------------------------------------------------


def _read_asset(filename: str) -> str:
    """Read a text file bundled in ``speks/assets/``."""
    ref = importlib.resources.files("speks").joinpath("assets", filename)
    return Path(str(ref)).read_text(encoding="utf-8")


WIDGET_CSS = _read_asset("speks.css")

# ---------------------------------------------------------------------------
# Diagram placeholder (standalone only)
# ---------------------------------------------------------------------------

DIAGRAM_PLACEHOLDER_CSS = """\
.speks-diagram-placeholder {
  background: #f5f5f5; border: 1px dashed #bdbdbd; border-radius: 6px;
  padding: 1rem; margin: 1rem 0; color: #757575; font-style: italic;
}
"""

# ---------------------------------------------------------------------------
# Standalone base styles (HTML reset, typography, tables, code)
# ---------------------------------------------------------------------------

STANDALONE_BASE_CSS = """\
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  line-height: 1.6;
  color: #212121;
  background: #fff;
  max-width: 860px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}
.md-logo img { height: 3rem !important; }
h1, h2, h3, h4 { color: #1976D2; }
h1 { border-bottom: 2px solid #e0e0e0; padding-bottom: .4rem; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 2rem 0; }
code {
  background: #f5f5f5; padding: .15rem .4rem;
  border-radius: 3px; font-size: .9em;
}
pre {
  background: #f5f5f5; border: 1px solid #e0e0e0;
  border-radius: 6px; padding: 1rem;
  overflow-x: auto;
}
pre code { background: none; padding: 0; }
table {
  width: 100%; border-collapse: collapse;
  font-size: .92rem; margin: 1rem 0;
}
th, td {
  padding: .45rem .7rem; text-align: left;
  border-bottom: 1px solid #e0e0e0;
}
th { background: #f5f5f5; font-weight: 600; }
"""

# Standalone overrides: playground is non-interactive (no server-side API).
STANDALONE_OVERRIDES_CSS = """\
.speks-run-btn { opacity: .6; cursor: default; transition: none; }
.speks-run-btn:hover { opacity: .6; }
.speks-result { display: none !important; }
"""
