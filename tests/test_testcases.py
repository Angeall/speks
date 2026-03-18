"""Tests for the test-case CRUD module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speks.core.testcases import TestCase, delete_testcase, load_testcases, save_testcase


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Minimal project with speks.toml."""
    (tmp_path / "speks.toml").write_text(
        '[project]\nname = "test"\ntestcases_dir = "testcases"\n',
        encoding="utf-8",
    )
    return tmp_path


class TestLoadTestcases:
    def test_returns_empty_when_no_file(self, project: Path) -> None:
        assert load_testcases(project, "some_func") == []

    def test_loads_existing_cases(self, project: Path) -> None:
        tc_dir = project / "testcases"
        tc_dir.mkdir()
        (tc_dir / "myfunc.json").write_text(
            json.dumps([
                {"id": "tc-1", "name": "case one", "inputs": {"x": 1},
                 "mocks": {}, "expected": 42},
            ]),
            encoding="utf-8",
        )
        cases = load_testcases(project, "myfunc")
        assert len(cases) == 1
        assert cases[0].id == "tc-1"
        assert cases[0].name == "case one"
        assert cases[0].inputs == {"x": 1}
        assert cases[0].expected == 42


class TestSaveTestcase:
    def test_creates_dir_and_file(self, project: Path) -> None:
        tc = TestCase(id="", name="first", inputs={"a": 1}, mocks={}, expected=True)
        saved = save_testcase(project, "evaluer", tc)

        assert saved.id.startswith("tc-")
        assert saved.name == "first"

        path = project / "testcases" / "evaluer.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["id"] == saved.id

    def test_appends_to_existing(self, project: Path) -> None:
        tc1 = TestCase(id="", name="first", inputs={"a": 1}, mocks={}, expected=1)
        tc2 = TestCase(id="", name="second", inputs={"a": 2}, mocks={}, expected=2)
        save_testcase(project, "fn", tc1)
        save_testcase(project, "fn", tc2)

        cases = load_testcases(project, "fn")
        assert len(cases) == 2
        assert cases[0].name == "first"
        assert cases[1].name == "second"

    def test_preserves_explicit_id(self, project: Path) -> None:
        tc = TestCase(id="my-id", name="named", inputs={}, mocks={}, expected=None)
        saved = save_testcase(project, "fn", tc)
        assert saved.id == "my-id"


class TestDeleteTestcase:
    def test_deletes_existing(self, project: Path) -> None:
        tc = TestCase(id="tc-abc", name="to delete", inputs={}, mocks={}, expected=0)
        save_testcase(project, "fn", tc)

        assert delete_testcase(project, "fn", "tc-abc") is True
        assert load_testcases(project, "fn") == []

    def test_returns_false_when_not_found(self, project: Path) -> None:
        tc = TestCase(id="tc-keep", name="keep", inputs={}, mocks={}, expected=0)
        save_testcase(project, "fn", tc)

        assert delete_testcase(project, "fn", "tc-nope") is False
        assert len(load_testcases(project, "fn")) == 1


class TestErrorMocks:
    """Tests for the error_mocks field on TestCase."""

    def test_default_error_mocks_is_empty(self) -> None:
        tc = TestCase(id="tc-1", name="t", inputs={}, mocks={}, expected=None)
        assert tc.error_mocks == {}

    def test_save_and_load_with_error_mocks(self, project: Path) -> None:
        error_cfg = {"SvcA": {"error_code": "FAIL", "error_message": "boom", "http_code": 500}}
        tc = TestCase(
            id="", name="err test", inputs={"x": 1}, mocks={},
            expected=None, error_mocks=error_cfg,
        )
        saved = save_testcase(project, "fn_err", tc)
        assert saved.error_mocks == error_cfg

        loaded = load_testcases(project, "fn_err")
        assert len(loaded) == 1
        assert loaded[0].error_mocks == error_cfg

    def test_backward_compat_missing_error_mocks(self, project: Path) -> None:
        """Old JSON files without error_mocks should load with empty dict."""
        tc_dir = project / "testcases"
        tc_dir.mkdir()
        (tc_dir / "old_func.json").write_text(
            json.dumps([
                {"id": "tc-old", "name": "old case", "inputs": {"x": 1},
                 "mocks": {}, "expected": 42},
            ]),
            encoding="utf-8",
        )
        cases = load_testcases(project, "old_func")
        assert len(cases) == 1
        assert cases[0].error_mocks == {}

    def test_expected_result_stored(self, project: Path) -> None:
        """Verify expected is saved and compared correctly."""
        tc = TestCase(
            id="", name="with expected", inputs={"x": 1}, mocks={},
            expected={"approuve": True, "score": 720},
        )
        saved = save_testcase(project, "fn_exp", tc)
        loaded = load_testcases(project, "fn_exp")
        assert loaded[0].expected == {"approuve": True, "score": 720}

    def test_error_mocks_persisted_on_disk(self, project: Path) -> None:
        error_cfg = {"SvcB": {"error_code": "TIMEOUT", "error_message": "timeout", "http_code": 504}}
        tc = TestCase(
            id="tc-disk", name="disk test", inputs={}, mocks={},
            expected=None, error_mocks=error_cfg,
        )
        save_testcase(project, "fn_disk", tc)

        path = project / "testcases" / "fn_disk.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw[0]["error_mocks"] == error_cfg
