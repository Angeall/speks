"""Shared fixtures for Speks end-to-end tests.

Boots the dev server against the ``credit-evaluation`` example project
once per session, exposes its base URL, and configures Playwright.

Marker: every test in this directory must be decorated with
``@pytest.mark.e2e`` (or live under ``tests/e2e``) so that the default
pytest invocation (``-m 'not e2e'`` in ``pyproject.toml``) skips them.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Auto-mark every test in this folder as ``e2e``.
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


# ---------------------------------------------------------------------------
# Project root + working copy
# ---------------------------------------------------------------------------


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_SRC = _PROJECT_ROOT / "examples" / "credit-evaluation"


@pytest.fixture(scope="session")
def credit_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the credit-evaluation example to a temp dir.

    Working from a copy keeps the in-repo example clean — tests may
    create files under ``testcases/`` or rebuild ``site/``.
    """
    workspace = tmp_path_factory.mktemp("speks_e2e_credit")
    for sub in ("src", "docs", "diagrams"):
        shutil.copytree(_EXAMPLE_SRC / sub, workspace / sub)
    speks_toml = _EXAMPLE_SRC / "speks.toml"
    if speks_toml.is_file():
        shutil.copy2(speks_toml, workspace / "speks.toml")
    return workspace


# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_http(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if resp.status < 500:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_err = exc
            time.sleep(0.3)
    raise RuntimeError(f"Server at {url} did not become ready within {timeout}s: {last_err}")


@pytest.fixture(scope="session")
def speks_server(credit_workspace: Path) -> Iterator[str]:
    """Start a Speks dev server on a free port and return its base URL.

    Uses the in-process FastAPI app via ``uvicorn`` in a daemon thread —
    no subprocess overhead, but isolates network state from the test.
    """
    from speks.web.builder import build_site
    from speks.web.server import create_app

    site_dir = build_site(credit_workspace)
    app = create_app(credit_workspace, site_dir)

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        _wait_for_http(f"{base_url}/", timeout=20.0)
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Playwright browser configuration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Default Playwright context: headless, English locale, no animations."""
    return {
        **browser_context_args,
        "locale": "en-US",
        "viewport": {"width": 1280, "height": 800},
    }
