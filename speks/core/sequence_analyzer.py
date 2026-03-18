"""Sequence diagram generator from Python AST.

Walks a function body **in order** and builds a list of
:class:`SequenceStep` objects that represent:

* service calls  (``ServiceClass().call(...)``)
* function calls (``other_function(...)``)
* conditional blocks (``if … / elif … / else``)

These steps are then rendered as a **Mermaid sequence diagram** with
``opt`` / ``alt`` fragments for conditional branches.
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from speks.core.dependency_analyzer import (
    DependencyGraph,
    ServiceNode,
    analyze_directory,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ServiceCallStep:
    """A call to an ExternalService."""

    caller: str
    service_name: str
    display_name: str
    args_text: str = ""


@dataclass
class FunctionCallStep:
    """A call to another business-rule function."""

    caller: str
    callee: str
    args_text: str = ""


@dataclass
class ReturnStep:
    """A return statement."""

    caller: str
    value_text: str = ""


@dataclass
class ConditionalBlock:
    """An ``if`` / ``elif`` / ``else`` block.

    *branches* is a list of ``(condition_text, steps)`` pairs.
    The last branch may have ``condition_text == ""`` for the ``else``.
    """

    branches: list[tuple[str, list[Any]]] = field(default_factory=list)


# Alias for type hints
SequenceStep = ServiceCallStep | FunctionCallStep | ReturnStep | ConditionalBlock


# ---------------------------------------------------------------------------
# AST → SequenceStep list
# ---------------------------------------------------------------------------


def extract_sequence(
    func_name: str,
    graph: DependencyGraph,
    src_dir: Path,
    project_root: Path,
) -> tuple[list[SequenceStep], dict[str, ServiceNode]]:
    """Extract the ordered sequence of steps from *func_name*.

    Returns ``(steps, participants)`` where *participants* maps service
    class names to their :class:`ServiceNode` (for display names).
    """
    # Find the function AST node
    func_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    all_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    for py_file in sorted(src_dir.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_functions[node.name] = node
                if node.name == func_name:
                    func_node = node

    if func_node is None:
        return [], {}

    participants: dict[str, ServiceNode] = {}
    steps = _walk_body(func_node.body, func_name, graph, all_functions, participants)
    return steps, participants


def _walk_body(
    body: list[ast.stmt],
    current_func: str,
    graph: DependencyGraph,
    all_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    participants: dict[str, ServiceNode],
) -> list[SequenceStep]:
    """Walk a list of statements and extract sequence steps in order."""
    steps: list[SequenceStep] = []

    for stmt in body:
        if isinstance(stmt, ast.If):
            block = _process_if(stmt, current_func, graph, all_functions, participants)
            if _block_has_calls(block):
                steps.append(block)
            continue

        if isinstance(stmt, ast.Return):
            if stmt.value is not None:
                # Extract calls embedded in the return expression first
                for node in ast.walk(stmt.value):
                    if isinstance(node, ast.Call):
                        step = _classify_call(
                            node, current_func, graph, all_functions, participants,
                        )
                        if step is not None:
                            steps.append(step)
            continue

        # Look for calls in assignments and expression statements
        call_nodes = _extract_calls_from_stmt(stmt)
        for call_node in call_nodes:
            step = _classify_call(call_node, current_func, graph, all_functions, participants)
            if step is not None:
                steps.append(step)

    return steps


def _process_if(
    node: ast.If,
    current_func: str,
    graph: DependencyGraph,
    all_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    participants: dict[str, ServiceNode],
) -> ConditionalBlock:
    """Convert an ``if`` / ``elif`` / ``else`` chain into a ConditionalBlock."""
    block = ConditionalBlock()

    # if branch
    cond_text = _unparse_safe(node.test)
    if_steps = _walk_body(node.body, current_func, graph, all_functions, participants)
    block.branches.append((cond_text, if_steps))

    # elif / else chain
    orelse = node.orelse
    while orelse:
        if len(orelse) == 1 and isinstance(orelse[0], ast.If):
            # elif
            elif_node = orelse[0]
            elif_cond = _unparse_safe(elif_node.test)
            elif_steps = _walk_body(elif_node.body, current_func, graph, all_functions, participants)
            block.branches.append((elif_cond, elif_steps))
            orelse = elif_node.orelse
        else:
            # else
            else_steps = _walk_body(orelse, current_func, graph, all_functions, participants)
            block.branches.append(("", else_steps))
            break

    return block


def _extract_calls_from_stmt(stmt: ast.stmt) -> list[ast.Call]:
    """Extract all Call nodes from a statement (top-level only, not nested ifs)."""
    calls: list[ast.Call] = []
    # For Assign: x = Something().call(...)
    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        value = stmt.value if isinstance(stmt, ast.Assign) else stmt.value
        if value is not None:
            for node in ast.walk(value):
                if isinstance(node, ast.Call):
                    calls.append(node)
    # For Expr: Something().call(...) standalone
    elif isinstance(stmt, ast.Expr):
        if isinstance(stmt.value, ast.Call):
            calls.append(stmt.value)
            # Also check nested calls (e.g. the outer call wraps a .call())
            for node in ast.walk(stmt.value):
                if isinstance(node, ast.Call) and node is not stmt.value:
                    calls.append(node)
    return calls


def _classify_call(
    node: ast.Call,
    current_func: str,
    graph: DependencyGraph,
    all_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    participants: dict[str, ServiceNode],
) -> SequenceStep | None:
    """Classify a call node as a service call, function call, or None."""
    # Pattern: ServiceClass().call(...)
    if isinstance(node.func, ast.Attribute) and node.func.attr == "call":
        inner = node.func.value
        if isinstance(inner, ast.Call):
            svc_name = None
            if isinstance(inner.func, ast.Name):
                svc_name = inner.func.id
            elif isinstance(inner.func, ast.Attribute):
                svc_name = inner.func.attr
            if svc_name and svc_name in graph.services:
                svc = graph.services[svc_name]
                participants[svc_name] = svc
                args_text = _unparse_args(node)
                return ServiceCallStep(
                    caller=current_func,
                    service_name=svc_name,
                    display_name=svc.display_name,
                    args_text=args_text,
                )

    # Pattern: other_function(...)
    if isinstance(node.func, ast.Name):
        callee = node.func.id
        if callee in graph.functions and callee != current_func:
            args_text = _unparse_args(node)
            return FunctionCallStep(
                caller=current_func,
                callee=callee,
                args_text=args_text,
            )

    return None


def _block_has_calls(block: ConditionalBlock) -> bool:
    """Check if a conditional block contains any meaningful steps."""
    for _, steps in block.branches:
        if steps:
            return True
    return False


def _unparse_safe(node: ast.expr) -> str:
    """Safely unparse an AST expression to source text."""
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def _unparse_args(call: ast.Call) -> str:
    """Unparse the arguments of a call to a readable string."""
    parts: list[str] = []
    for arg in call.args:
        parts.append(_unparse_safe(arg))
    for kw in call.keywords:
        if kw.arg:
            parts.append(f"{kw.arg}={_unparse_safe(kw.value)}")
        else:
            parts.append(f"**{_unparse_safe(kw.value)}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Mermaid rendering
# ---------------------------------------------------------------------------


def render_sequence_mermaid(
    func_name: str,
    steps: list[SequenceStep],
    participants: dict[str, ServiceNode],
    called_functions: set[str] | None = None,
) -> str:
    """Render a Mermaid sequence diagram from extracted steps.

    Parameters
    ----------
    func_name:
        The entry-point function name.
    steps:
        The ordered list of sequence steps.
    participants:
        Map of service class names to ServiceNode (for display names).
    called_functions:
        Set of function names that appear as callees (for participant declaration).
    """
    if called_functions is None:
        called_functions = _collect_called_functions(steps)

    lines: list[str] = ["sequenceDiagram"]

    # Declare participants
    lines.append(f"    participant {func_name}")
    for fname in sorted(called_functions):
        lines.append(f"    participant {fname}")
    for svc_name in sorted(participants):
        svc = participants[svc_name]
        lines.append(f'    participant {svc_name} as {svc.display_name}')

    # Render steps
    _render_steps(lines, steps, func_name, indent=1)

    return "\n".join(lines)


def _render_steps(
    lines: list[str],
    steps: list[SequenceStep],
    current_func: str,
    indent: int,
) -> None:
    """Recursively render steps into Mermaid lines."""
    pad = "    " * indent

    for step in steps:
        if isinstance(step, ServiceCallStep):
            label = step.args_text or " "
            lines.append(f"{pad}{current_func}->>+{step.service_name}: {label}")
            lines.append(f"{pad}{step.service_name}-->>-{current_func}: response")

        elif isinstance(step, FunctionCallStep):
            label = step.args_text or " "
            lines.append(f"{pad}{current_func}->>+{step.callee}: {label}")
            lines.append(f"{pad}{step.callee}-->>-{current_func}: result")

        elif isinstance(step, ReturnStep):
            pass  # Returns are implicit in sequence diagrams

        elif isinstance(step, ConditionalBlock):
            _render_conditional(lines, step, current_func, indent)


def _render_conditional(
    lines: list[str],
    block: ConditionalBlock,
    current_func: str,
    indent: int,
) -> None:
    """Render a conditional block as opt/alt fragments."""
    pad = "    " * indent

    if len(block.branches) == 1:
        # Simple if with no else → opt
        cond, if_steps = block.branches[0]
        lines.append(f"{pad}opt {cond}")
        _render_steps(lines, if_steps, current_func, indent + 1)
        lines.append(f"{pad}end")

    elif len(block.branches) == 2 and block.branches[1][0] == "":
        # if/else → alt
        cond, if_steps = block.branches[0]
        _, else_steps = block.branches[1]
        lines.append(f"{pad}alt {cond}")
        _render_steps(lines, if_steps, current_func, indent + 1)
        lines.append(f"{pad}else")
        _render_steps(lines, else_steps, current_func, indent + 1)
        lines.append(f"{pad}end")

    else:
        # if/elif/else → alt with multiple branches
        for i, (cond, branch_steps) in enumerate(block.branches):
            if i == 0:
                lines.append(f"{pad}alt {cond}")
            elif cond:
                lines.append(f"{pad}else {cond}")
            else:
                lines.append(f"{pad}else")
            _render_steps(lines, branch_steps, current_func, indent + 1)
        lines.append(f"{pad}end")


def _collect_called_functions(steps: list[SequenceStep]) -> set[str]:
    """Collect all function names referenced in steps (recursively)."""
    result: set[str] = set()
    for step in steps:
        if isinstance(step, FunctionCallStep):
            result.add(step.callee)
        elif isinstance(step, ConditionalBlock):
            for _, branch_steps in step.branches:
                result.update(_collect_called_functions(branch_steps))
    return result


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------


def generate_sequence_diagram(
    func_name: str,
    src_dir: Path,
    project_root: Path,
) -> str | None:
    """Generate a Mermaid sequence diagram for *func_name*.

    Returns the Mermaid source string, or ``None`` if the function
    cannot be found or has no interesting steps.
    """
    graph = analyze_directory(src_dir, project_root)

    if func_name not in graph.functions:
        return None

    steps, participants = extract_sequence(func_name, graph, src_dir, project_root)
    if not steps and not participants:
        return None

    return render_sequence_mermaid(func_name, steps, participants)
