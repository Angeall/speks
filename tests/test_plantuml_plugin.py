"""Tests for the PlantUML plugin (encoding + HTML replacement)."""

from unittest.mock import MagicMock

import pytest

from speks.mkdocs_plugins.plantuml import (
    SpeksPlantUMLPlugin,
    plantuml_encode,
    _render_plantuml_block,
    _strip_html_tags,
)


class TestPlantUMLEncode:
    def test_simple_diagram(self) -> None:
        source = "@startuml\nA -> B\n@enduml"
        encoded = plantuml_encode(source)
        # Should produce a non-empty alphanumeric string
        assert len(encoded) > 0
        assert all(c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_" for c in encoded)

    def test_deterministic(self) -> None:
        source = "@startuml\nAlice -> Bob: Hello\n@enduml"
        assert plantuml_encode(source) == plantuml_encode(source)

    def test_different_sources_differ(self) -> None:
        a = plantuml_encode("@startuml\nA -> B\n@enduml")
        b = plantuml_encode("@startuml\nX -> Y\n@enduml")
        assert a != b

    def test_unicode_support(self) -> None:
        source = "@startuml\nacteur Système\n@enduml"
        encoded = plantuml_encode(source)
        assert len(encoded) > 0


class TestStripHtmlTags:
    def test_removes_spans(self) -> None:
        html = '<span class="k">@startuml</span>\n<span>A</span>'
        assert _strip_html_tags(html) == "@startuml\nA"

    def test_unescapes_entities(self) -> None:
        html = "A -&gt; B : &amp; hello"
        assert _strip_html_tags(html) == "A -> B : & hello"

    def test_preserves_plain_text(self) -> None:
        assert _strip_html_tags("hello world") == "hello world"


class TestRenderBlock:
    def test_generates_img_tag(self) -> None:
        result = _render_plantuml_block("@startuml\nA -> B\n@enduml", "https://plantuml.example.com")
        assert '<img src="https://plantuml.example.com/svg/' in result
        assert "speks-plantuml-diagram" in result

    def test_generates_fallback(self) -> None:
        result = _render_plantuml_block("@startuml\nA -> B\n@enduml", "https://plantuml.example.com")
        assert "speks-plantuml-fallback" in result
        assert "onerror" in result

    def test_generates_source_details(self) -> None:
        result = _render_plantuml_block("@startuml\nA -> B\n@enduml", "https://plantuml.example.com")
        assert "PlantUML Source" in result
        assert "@startuml" in result

    def test_escapes_html_in_source(self) -> None:
        result = _render_plantuml_block("@startuml\nnote: <b>bold</b>\n@enduml", "https://x.com")
        assert "&lt;b&gt;bold&lt;/b&gt;" in result


class TestPluginPostPage:
    def test_replaces_plantuml_code_block(self) -> None:
        plugin = SpeksPlantUMLPlugin()
        plugin.config = MagicMock()
        plugin.config.server = "https://plantuml.example.com"

        html = (
            '<html><head></head><body>'
            '<pre><code class="language-plantuml">'
            "@startuml\nA -&gt; B\n@enduml"
            "</code></pre>"
            "</body></html>"
        )
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        assert "speks-plantuml-diagram" in result
        assert "plantuml.example.com/svg/" in result
        # CSS is now served via extra_css, not inline <style>
        assert "<style>" not in result

    def test_replaces_superfence_format(self) -> None:
        plugin = SpeksPlantUMLPlugin()
        plugin.config = MagicMock()
        plugin.config.server = "https://plantuml.example.com"

        html = (
            '<html><head></head><body>'
            '<pre class="plantuml"><code>'
            "@startuml\nX -&gt; Y\n@enduml"
            "</code></pre>"
            "</body></html>"
        )
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        assert "speks-plantuml-diagram" in result

    def test_skips_non_plantuml_pages(self) -> None:
        plugin = SpeksPlantUMLPlugin()
        plugin.config = MagicMock()
        plugin.config.server = "https://plantuml.example.com"

        html = "<html><head></head><body><p>No diagrams</p></body></html>"
        page = MagicMock()
        config = MagicMock()
        result = plugin.on_post_page(html, page=page, config=config)
        assert result == html
