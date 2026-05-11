"""Smoke test: the dev server starts and serves the home page."""

from __future__ import annotations

import urllib.request


def test_server_responds(speks_server: str) -> None:
    with urllib.request.urlopen(f"{speks_server}/", timeout=5.0) as resp:
        assert resp.status == 200
        body = resp.read().decode("utf-8", errors="replace")
        # Material theme always emits this; if it's there, MkDocs build ran.
        assert "<html" in body.lower()


def test_credit_rules_page_loads(speks_server: str, page) -> None:
    page.goto(f"{speks_server}/credit-rules/")
    # Wait for the page to render
    page.wait_for_load_state("networkidle")
    # Any of the function names should appear somewhere on the page
    assert page.locator("body").inner_text().lower().count("evaluate_credit") > 0
