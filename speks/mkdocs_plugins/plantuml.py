"""MkDocs plugin that renders PlantUML fenced blocks as SVG images.

The tags plugin emits ````` ```plantuml ````` blocks.  This plugin converts
them into ``<img>`` tags pointing at a PlantUML server (default: public)
and wraps the raw source in a collapsible ``<details>`` block.

The plugin works at the **on_post_page** level so it processes the final
HTML after all Markdown extensions have run.

Configuration (in ``mkdocs.yml``)::

    plugins:
      - speks-plantuml:
          server: "https://www.plantuml.com/plantuml"
          # or a local server: "http://localhost:8080"
"""

from __future__ import annotations

import re
import zlib
from html import unescape
from typing import Any

from mkdocs.config.base import Config
from mkdocs.config.config_options import Type as MkType
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

from speks.i18n import t

# ---------------------------------------------------------------------------
# PlantUML text encoding  (deflate → custom base64)
# ---------------------------------------------------------------------------

_PLANTUML_ALPHABET = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "-_"
)


def _encode_6bit(b: int) -> str:
    """Encode a 6-bit value using PlantUML's alphabet."""
    return _PLANTUML_ALPHABET[b & 0x3F]


def _encode_3bytes(b1: int, b2: int, b3: int) -> str:
    """Encode 3 bytes into 4 PlantUML base64 characters."""
    c1 = b1 >> 2
    c2 = ((b1 & 0x3) << 4) | (b2 >> 4)
    c3 = ((b2 & 0xF) << 2) | (b3 >> 6)
    c4 = b3 & 0x3F
    return _encode_6bit(c1) + _encode_6bit(c2) + _encode_6bit(c3) + _encode_6bit(c4)


def plantuml_encode(text: str) -> str:
    """Encode PlantUML source text into the URL-safe format.

    This matches the encoding used by the official PlantUML server:
    UTF-8 → raw deflate → custom base64.
    """
    data = zlib.compress(text.encode("utf-8"))[2:-4]  # raw deflate (strip zlib header/checksum)

    encoded = []
    i = 0
    while i < len(data):
        if i + 2 < len(data):
            encoded.append(_encode_3bytes(data[i], data[i + 1], data[i + 2]))
        elif i + 1 < len(data):
            encoded.append(_encode_3bytes(data[i], data[i + 1], 0))
        else:
            encoded.append(_encode_3bytes(data[i], 0, 0))
        i += 3

    return "".join(encoded)


# ---------------------------------------------------------------------------
# HTML regex to find rendered plantuml code blocks
# ---------------------------------------------------------------------------

# After pymdownx.superfences, a ```plantuml block becomes either:
# - <pre><code class="language-plantuml">...</code></pre>
# - or a <div> with highlight class
# We also handle the case from codehilite or plain fenced_code.

_PLANTUML_BLOCK_RE = re.compile(
    r'<pre[^>]*>\s*<code[^>]*class="[^"]*language-plantuml[^"]*"[^>]*>'
    r"(?P<source>.*?)"
    r"</code>\s*</pre>",
    re.DOTALL,
)

# Also handle blocks rendered by superfences custom fence format:
_PLANTUML_SUPERFENCE_RE = re.compile(
    r'<pre[^>]*class="[^"]*plantuml[^"]*"[^>]*>\s*<code[^>]*>'
    r"(?P<source>.*?)"
    r"</code>\s*</pre>",
    re.DOTALL,
)


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags (e.g. <span> from syntax highlighting) and unescape entities."""
    cleaned = re.sub(r"<[^>]+>", "", text)
    return unescape(cleaned).strip()


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class PluginConfig(Config):  # type: ignore[no-untyped-call]
    server = MkType(str, default="https://www.plantuml.com/plantuml")


class SpeksPlantUMLPlugin(BasePlugin[PluginConfig]):  # type: ignore[no-untyped-call]
    """Convert PlantUML code blocks to SVG images at build time."""

    def on_post_page(
        self,
        output: str,
        *,
        page: Page,
        config: MkDocsConfig,
    ) -> str:
        server = self.config.server.rstrip("/")
        replaced = False

        def _replace(match: re.Match[str]) -> str:
            nonlocal replaced
            raw = _strip_html_tags(match.group("source"))
            if not raw:
                return match.group(0)
            replaced = True
            return _render_plantuml_block(raw, server)

        output = _PLANTUML_BLOCK_RE.sub(_replace, output)
        output = _PLANTUML_SUPERFENCE_RE.sub(_replace, output)

        return output


def _render_plantuml_block(source: str, server: str) -> str:
    """Produce an ``<img>`` tag + collapsible raw source for a PlantUML diagram."""
    encoded = plantuml_encode(source)
    img_url = f"{server}/svg/{encoded}"

    # Escape source for safe HTML embedding
    safe_source = (
        source
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    return f"""\
<div class="speks-plantuml-diagram">
  <img src="{img_url}" alt="{t("plantuml.alt")}" loading="lazy"
       onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
  <div class="speks-plantuml-fallback" style="display:none;">
    <pre><code>{safe_source}</code></pre>
  </div>
  <details class="speks-plantuml-source">
    <summary>{t("plantuml.source_label")}</summary>
    <pre><code>{safe_source}</code></pre>
  </details>
</div>"""
