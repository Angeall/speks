"""E2E tests for @[mermaid] and @[plantuml] tag rendering."""

from __future__ import annotations

from playwright.sync_api import Page, expect


# ---------------------------------------------------------------------------
# @[mermaid]  — embeds a .mmd file as a Mermaid block
# ---------------------------------------------------------------------------


class TestMermaidTag:
    def test_mermaid_block_present(self, speks_server: str, page: Page) -> None:
        page.goto(f"{speks_server}/architecture/")
        page.wait_for_load_state("networkidle")
        # Material renders fenced ``` mermaid blocks as <pre class="mermaid">
        # (superfences style) or <div class="mermaid">.
        mermaid_blocks = page.locator(
            "pre.mermaid, div.mermaid, [class~='mermaid']",
        )
        assert mermaid_blocks.count() >= 1, "No mermaid container rendered"

    def test_mermaid_source_is_embedded(
        self, speks_server: str, page: Page,
    ) -> None:
        # Either the SVG has been rendered by Mermaid.js, or the raw source
        # is still in the <pre>.  In either case the container is present
        # and the diagram is wired up.  We check the source in the served
        # HTML (before JS runs) to be CDN-independent.
        import urllib.request

        html = urllib.request.urlopen(
            f"{speks_server}/architecture/", timeout=5.0,
        ).read().decode("utf-8", errors="replace")
        # The Mermaid block source contains a header like "graph LR" or
        # "flowchart TD".
        assert any(
            kw in html
            for kw in ("graph LR", "graph TD", "flowchart ", "sequenceDiagram")
        ), "No Mermaid diagram source in served HTML"

    def test_mermaid_renders_svg_eventually(
        self, speks_server: str, page: Page,
    ) -> None:
        """Best-effort: wait up to 20s for Mermaid.js to inject an SVG.

        Skipped silently if the browser can't reach the CDN (offline CI).
        """
        page.goto(f"{speks_server}/architecture/")
        page.wait_for_load_state("networkidle")
        try:
            page.wait_for_function(
                "() => document.querySelectorAll("
                "  'pre.mermaid svg, div.mermaid svg, .mermaid > svg'"
                ").length > 0",
                timeout=20_000,
            )
        except Exception:
            import pytest

            pytest.skip("Mermaid CDN unavailable — SVG never rendered")
        svgs = page.locator(".mermaid svg, pre.mermaid svg, div.mermaid svg")
        assert svgs.count() >= 1


# ---------------------------------------------------------------------------
# @[plantuml]  — embeds a .puml file as an <img> from a PlantUML server
# ---------------------------------------------------------------------------


class TestPlantumlTag:
    def test_plantuml_image_rendered(self, speks_server: str, page: Page) -> None:
        page.goto(f"{speks_server}/architecture/")
        page.wait_for_load_state("networkidle")
        # The PlantUML plugin emits <div class="speks-plantuml-diagram">
        # containing an <img src="https://www.plantuml.com/plantuml/svg/...">.
        diagram = page.locator(".speks-plantuml-diagram")
        expect(diagram.first).to_be_visible()
        img = diagram.first.locator("img")
        expect(img).to_be_visible()
        src = img.get_attribute("src") or ""
        assert "plantuml" in src.lower(), f"Unexpected src: {src!r}"

    def test_plantuml_source_collapsed_below_image(
        self, speks_server: str, page: Page,
    ) -> None:
        page.goto(f"{speks_server}/architecture/")
        page.wait_for_load_state("networkidle")
        diagram = page.locator(".speks-plantuml-diagram").first
        # The raw source is in a <details> sibling — collapsed by default.
        details = diagram.locator("details")
        assert details.count() >= 1
        # Expand it; the inner <pre> must contain @startuml.
        details.first.evaluate("el => el.open = true")
        pre = details.first.locator("pre")
        assert "@startuml" in (pre.text_content() or "")
