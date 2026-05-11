"""Pytest root configuration shared by all tests.

Conditionally skips collection of the ``tests/e2e`` suite when Playwright
isn't installed (the main CI job only depends on ``[dev]``).  Installing
``[e2e]`` enables the suite automatically.
"""

from __future__ import annotations

import importlib.util

collect_ignore_glob: list[str] = []

if importlib.util.find_spec("playwright") is None:
    collect_ignore_glob.append("e2e/*")
