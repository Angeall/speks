"""E2E tests for @[sequence] and @[dependencies] tag rendering.

Both tags produce Mermaid diagrams that are turned into ``<pre class="mermaid">``
blocks by MkDocs.  We check the embedded source in the served HTML (browser-
independent) plus the DOM container (Playwright-based).
"""

from __future__ import annotations

import urllib.request

from playwright.sync_api import Page


# ---------------------------------------------------------------------------
# @[sequence]
# ---------------------------------------------------------------------------


class TestSequenceTag:
    def test_sequence_block_present(self, speks_server: str, page: Page) -> None:
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        # At least one Mermaid container must be on the page.
        mermaid = page.locator("pre.mermaid, div.mermaid")
        assert mermaid.count() >= 1

    def test_sequence_source_includes_participants(
        self, speks_server: str,
    ) -> None:
        # @[sequence](src/credit.py:evaluate_credit) → sequenceDiagram with
        # the CoreBanking entity as a participant.  Inspect served HTML so
        # the assertion does not depend on Mermaid.js rendering.
        html = urllib.request.urlopen(
            f"{speks_server}/credit-rules/", timeout=5.0,
        ).read().decode("utf-8", errors="replace")
        assert "sequenceDiagram" in html
        # The CoreBanking.check_balance stub is sanitised to
        # ``CoreBanking__check_balance`` for Mermaid id-safety.
        assert "CoreBanking__check_balance" in html
        # The display name (``CoreBanking / check_balance``) appears as the
        # ``participant ... as`` label.
        assert "CoreBanking / check_balance" in html


# ---------------------------------------------------------------------------
# @[dependencies]
# ---------------------------------------------------------------------------


class TestDependenciesTag:
    def test_dependency_graph_block_present(
        self, speks_server: str, page: Page,
    ) -> None:
        page.goto(f"{speks_server}/architecture/")
        page.wait_for_load_state("networkidle")
        # The first @[dependencies](src/) on architecture.md renders a
        # full graph; later tags render focused subgraphs.  Multiple
        # mermaid containers expected.
        mermaid = page.locator("pre.mermaid, div.mermaid")
        assert mermaid.count() >= 2

    def test_dependency_source_includes_entity_nodes(
        self, speks_server: str,
    ) -> None:
        html = urllib.request.urlopen(
            f"{speks_server}/architecture/", timeout=5.0,
        ).read().decode("utf-8", errors="replace")
        # graph LR is the default direction for the dependency renderer.
        assert "graph LR" in html
        # CoreBanking.check_balance must appear as a node (sanitised id).
        assert "CoreBanking__check_balance" in html
        # The :::service class is applied to stub nodes; the legend
        # references it via the same class def.
        assert "classDef service" in html

    def test_dependency_legend_rendered(
        self, speks_server: str, page: Page,
    ) -> None:
        # The dependencies plugin prepends a legend admonition before the
        # first dependency graph.  Material wraps admonitions in a
        # <div class="admonition info">.
        page.goto(f"{speks_server}/architecture/")
        page.wait_for_load_state("networkidle")
        admonitions = page.locator(".admonition")
        assert admonitions.count() >= 1, "No admonition legend rendered"
