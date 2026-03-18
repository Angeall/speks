"""CRUD helpers for playground test cases.

Test cases are stored as JSON files under the project's ``testcases/``
directory (configurable via ``speks.toml``).  Each function gets its own
file: ``testcases/{function_name}.json``.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from speks.core.config import load_config


# Only allow simple identifiers as function names (no path separators, dots, etc.)
_SAFE_FUNC_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class TestCase:
    """A single saved playground test case."""

    id: str
    name: str
    inputs: dict[str, Any]
    mocks: dict[str, Any]
    expected: Any
    error_mocks: dict[str, Any] = field(default_factory=dict)


def _validate_func_name(func_name: str) -> None:
    """Raise ValueError if *func_name* is not a safe Python identifier."""
    if not _SAFE_FUNC_NAME.match(func_name):
        raise ValueError(f"Invalid function name: {func_name!r}")


def _testcases_path(project_root: Path, func_name: str) -> Path:
    """Return the JSON file path for *func_name*'s test cases."""
    _validate_func_name(func_name)
    config = load_config(project_root)
    tc_dir = project_root / config.testcases_dir
    return tc_dir / f"{func_name}.json"


def load_testcases(project_root: Path, func_name: str) -> list[TestCase]:
    """Load all test cases for *func_name*.  Returns ``[]`` if none exist."""
    path = _testcases_path(project_root, func_name)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases: list[TestCase] = []
    for item in raw:
        # Backward compat: old files may lack error_mocks
        item.setdefault("error_mocks", {})
        cases.append(TestCase(**item))
    return cases


def save_testcase(
    project_root: Path,
    func_name: str,
    tc: TestCase,
) -> TestCase:
    """Append *tc* to the test-case file, generating an id if empty."""
    if not tc.id:
        tc = TestCase(
            id=f"tc-{uuid.uuid4().hex[:8]}",
            name=tc.name,
            inputs=tc.inputs,
            mocks=tc.mocks,
            expected=tc.expected,
            error_mocks=tc.error_mocks,
        )

    existing = load_testcases(project_root, func_name)
    existing.append(tc)

    path = _testcases_path(project_root, func_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(t) for t in existing], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return tc


def delete_testcase(
    project_root: Path,
    func_name: str,
    testcase_id: str,
) -> bool:
    """Remove the test case with *testcase_id*.  Returns True if found."""
    existing = load_testcases(project_root, func_name)
    filtered = [tc for tc in existing if tc.id != testcase_id]
    if len(filtered) == len(existing):
        return False

    path = _testcases_path(project_root, func_name)
    path.write_text(
        json.dumps([asdict(t) for t in filtered], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True
