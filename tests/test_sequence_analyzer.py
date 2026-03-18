"""Tests for the sequence diagram analyzer."""

import textwrap
from pathlib import Path

import pytest

from speks.core.sequence_analyzer import (
    ConditionalBlock,
    FunctionCallStep,
    ServiceCallStep,
    extract_sequence,
    generate_sequence_diagram,
    render_sequence_mermaid,
)
from speks.core.dependency_analyzer import analyze_directory


@pytest.fixture()
def simple_project(tmp_path: Path) -> Path:
    """Project with a single service call, no conditions."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "rules.py").write_text(
        textwrap.dedent("""\
            from speks import ExternalService, MockResponse

            class APIClient(ExternalService):
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="ok")

            def check(user_id: str) -> str:
                return APIClient().call(user_id)
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def conditional_project(tmp_path: Path) -> Path:
    """Project with conditional service calls (if/else)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "rules.py").write_text(
        textwrap.dedent("""\
            from speks import ExternalService, MockResponse

            class SvcA(ExternalService):
                component_name = "AppX"
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="a")

            class SvcB(ExternalService):
                component_name = "AppX"
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="b")

            class SvcC(ExternalService):
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="c")

            def process(x: str, mode: str) -> str:
                a = SvcA().call(x)
                if mode == "advanced":
                    b = SvcB().call(x)
                    return b
                else:
                    c = SvcC().call(x)
                    return c
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def opt_project(tmp_path: Path) -> Path:
    """Project with a simple if (no else) → opt block."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "rules.py").write_text(
        textwrap.dedent("""\
            from speks import ExternalService, MockResponse

            class SvcA(ExternalService):
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="a")

            class SvcB(ExternalService):
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="b")

            def process(x: str, flag: bool) -> str:
                a = SvcA().call(x)
                if flag:
                    b = SvcB().call(x)
                return a
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def funcall_project(tmp_path: Path) -> Path:
    """Project with cross-function calls."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "rules.py").write_text(
        textwrap.dedent("""\
            from speks import ExternalService, MockResponse

            class SvcA(ExternalService):
                def execute(self, x: str) -> str:
                    pass
                def mock(self, x: str) -> MockResponse:
                    return MockResponse(data="a")

            def helper(x: str) -> str:
                return SvcA().call(x)

            def main_func(x: str) -> str:
                result = helper(x)
                return result
        """),
        encoding="utf-8",
    )
    return tmp_path


class TestExtractSequence:
    def test_simple_service_call(self, simple_project: Path) -> None:
        graph = analyze_directory(simple_project / "src", simple_project)
        steps, participants = extract_sequence(
            "check", graph, simple_project / "src", simple_project,
        )
        assert len(steps) == 1
        assert isinstance(steps[0], ServiceCallStep)
        assert steps[0].service_name == "APIClient"
        assert "APIClient" in participants

    def test_conditional_branches(self, conditional_project: Path) -> None:
        graph = analyze_directory(conditional_project / "src", conditional_project)
        steps, participants = extract_sequence(
            "process", graph, conditional_project / "src", conditional_project,
        )
        # First: unconditional SvcA call
        assert isinstance(steps[0], ServiceCallStep)
        assert steps[0].service_name == "SvcA"
        # Second: conditional block
        assert isinstance(steps[1], ConditionalBlock)
        assert len(steps[1].branches) == 2  # if + else
        # if branch has SvcB
        if_steps = steps[1].branches[0][1]
        assert any(isinstance(s, ServiceCallStep) and s.service_name == "SvcB" for s in if_steps)
        # else branch has SvcC
        else_steps = steps[1].branches[1][1]
        assert any(isinstance(s, ServiceCallStep) and s.service_name == "SvcC" for s in else_steps)

    def test_opt_block(self, opt_project: Path) -> None:
        graph = analyze_directory(opt_project / "src", opt_project)
        steps, participants = extract_sequence(
            "process", graph, opt_project / "src", opt_project,
        )
        # Unconditional SvcA
        assert isinstance(steps[0], ServiceCallStep)
        assert steps[0].service_name == "SvcA"
        # Conditional block with single branch (opt)
        assert isinstance(steps[1], ConditionalBlock)
        assert len(steps[1].branches) == 1

    def test_function_call(self, funcall_project: Path) -> None:
        graph = analyze_directory(funcall_project / "src", funcall_project)
        steps, _ = extract_sequence(
            "main_func", graph, funcall_project / "src", funcall_project,
        )
        assert len(steps) == 1
        assert isinstance(steps[0], FunctionCallStep)
        assert steps[0].callee == "helper"

    def test_unknown_function_returns_empty(self, simple_project: Path) -> None:
        graph = analyze_directory(simple_project / "src", simple_project)
        steps, participants = extract_sequence(
            "nonexistent", graph, simple_project / "src", simple_project,
        )
        assert steps == []
        assert participants == {}

    def test_display_name_in_participants(self, conditional_project: Path) -> None:
        graph = analyze_directory(conditional_project / "src", conditional_project)
        _, participants = extract_sequence(
            "process", graph, conditional_project / "src", conditional_project,
        )
        assert participants["SvcA"].display_name == "AppX / SvcA"
        assert participants["SvcB"].display_name == "AppX / SvcB"


class TestRenderMermaid:
    def test_simple_diagram(self, simple_project: Path) -> None:
        graph = analyze_directory(simple_project / "src", simple_project)
        steps, participants = extract_sequence(
            "check", graph, simple_project / "src", simple_project,
        )
        mermaid = render_sequence_mermaid("check", steps, participants)
        assert "sequenceDiagram" in mermaid
        assert "participant check" in mermaid
        assert "participant APIClient" in mermaid
        assert "check->>+APIClient:" in mermaid
        assert "APIClient-->>-check: response" in mermaid

    def test_alt_block(self, conditional_project: Path) -> None:
        graph = analyze_directory(conditional_project / "src", conditional_project)
        steps, participants = extract_sequence(
            "process", graph, conditional_project / "src", conditional_project,
        )
        mermaid = render_sequence_mermaid("process", steps, participants)
        assert "alt " in mermaid
        assert "else" in mermaid
        assert "end" in mermaid
        # Both conditional services should appear
        assert "SvcB" in mermaid
        assert "SvcC" in mermaid

    def test_opt_block(self, opt_project: Path) -> None:
        graph = analyze_directory(opt_project / "src", opt_project)
        steps, participants = extract_sequence(
            "process", graph, opt_project / "src", opt_project,
        )
        mermaid = render_sequence_mermaid("process", steps, participants)
        assert "opt " in mermaid
        assert "end" in mermaid
        assert "SvcB" in mermaid

    def test_display_names_in_diagram(self, conditional_project: Path) -> None:
        graph = analyze_directory(conditional_project / "src", conditional_project)
        steps, participants = extract_sequence(
            "process", graph, conditional_project / "src", conditional_project,
        )
        mermaid = render_sequence_mermaid("process", steps, participants)
        assert "AppX / SvcA" in mermaid
        assert "AppX / SvcB" in mermaid

    def test_function_call_in_diagram(self, funcall_project: Path) -> None:
        graph = analyze_directory(funcall_project / "src", funcall_project)
        steps, participants = extract_sequence(
            "main_func", graph, funcall_project / "src", funcall_project,
        )
        mermaid = render_sequence_mermaid("main_func", steps, participants)
        assert "participant helper" in mermaid
        assert "main_func->>+helper:" in mermaid


class TestGenerateSequenceDiagram:
    def test_returns_mermaid_string(self, simple_project: Path) -> None:
        result = generate_sequence_diagram(
            "check", simple_project / "src", simple_project,
        )
        assert result is not None
        assert "sequenceDiagram" in result

    def test_returns_none_for_unknown_func(self, simple_project: Path) -> None:
        result = generate_sequence_diagram(
            "nonexistent", simple_project / "src", simple_project,
        )
        assert result is None

    def test_conditional_diagram(self, conditional_project: Path) -> None:
        result = generate_sequence_diagram(
            "process", conditional_project / "src", conditional_project,
        )
        assert result is not None
        assert "alt " in result
        assert "else" in result


class TestElifChain:
    def test_elif_generates_multi_alt(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "rules.py").write_text(
            textwrap.dedent("""\
                from speks import ExternalService, MockResponse

                class SvcA(ExternalService):
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="a")

                class SvcB(ExternalService):
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="b")

                class SvcC(ExternalService):
                    def execute(self, x: str) -> str:
                        pass
                    def mock(self, x: str) -> MockResponse:
                        return MockResponse(data="c")

                def multi(x: str, mode: int) -> str:
                    if mode == 1:
                        return SvcA().call(x)
                    elif mode == 2:
                        return SvcB().call(x)
                    else:
                        return SvcC().call(x)
            """),
            encoding="utf-8",
        )
        result = generate_sequence_diagram("multi", src, tmp_path)
        assert result is not None
        assert "alt mode == 1" in result
        assert "else mode == 2" in result
        assert "SvcA" in result
        assert "SvcB" in result
        assert "SvcC" in result
        # Should have exactly one 'end' for the alt block
        assert result.count("end") == 1


class TestSequencePlugin:
    def test_tag_resolution(self, simple_project: Path) -> None:
        from speks.mkdocs_plugins.sequence import _resolve_sequence

        result = _resolve_sequence("src/rules.py:check", simple_project)
        assert "```mermaid" in result
        assert "sequenceDiagram" in result

    def test_tag_missing_function(self, simple_project: Path) -> None:
        from speks.mkdocs_plugins.sequence import _resolve_sequence

        result = _resolve_sequence("src/rules.py:nope", simple_project)
        assert "<!-- speks-sequence:" in result

    def test_tag_missing_path(self, simple_project: Path) -> None:
        from speks.mkdocs_plugins.sequence import _resolve_sequence

        result = _resolve_sequence("nonexistent.py:func", simple_project)
        assert "<!-- speks-sequence: path not found" in result

    def test_tag_no_colon(self, simple_project: Path) -> None:
        from speks.mkdocs_plugins.sequence import _resolve_sequence

        result = _resolve_sequence("src/rules.py", simple_project)
        assert "<!-- speks-sequence: expected format" in result
