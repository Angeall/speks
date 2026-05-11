"""Static dependency analyzer for Speks projects.

Walks Python source files and builds a graph of:

- **Service entities** declared with ``@service`` and their **stub methods**
  declared with ``@stub(mock=..., error=...)``
- **Business-rule functions** (top-level ``def``) and which stubs/other
  functions they call
- **Cross-module imports** that create inter-file dependencies

The result is a :class:`DependencyGraph` that can be rendered as Mermaid,
filtered per function, or queried programmatically.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PydanticFieldInfo:
    """Schema for a single field of a Pydantic model used in mock data."""

    name: str
    annotation: str  # e.g. "str", "float", "int"
    default: Any = None  # default value from the constructor call


@dataclass
class ServiceNode:
    """A stub method on a ``@service``-decorated class.

    The ``name`` field is dotted: ``"EntityClass.method_name"``.
    ``component_name`` carries the entity class name (e.g. ``"CoreBanking"``)
    and ``method_name`` carries the bare method name.
    """

    name: str  # dotted: "ClassName.method_name"
    module: str  # relative file path, e.g. "src/credit.py"
    docstring: str | None = None  # method docstring (not class)
    mock_data_default: Any = None  # static value from @stub(mock=...)
    component_name: str | None = None  # entity class name (e.g. "CoreBanking")
    method_name: str | None = None  # bare method name (e.g. "check_balance")
    mock_error_default: dict[str, Any] | None = None  # parsed @stub(error=MockError(...))
    mock_pydantic_fields: list[PydanticFieldInfo] | None = None
    mock_pydantic_class: str | None = None

    @property
    def display_name(self) -> str:
        """Return ``ClassName / method_name`` for the playground UI."""
        if self.component_name and self.method_name:
            return f"{self.component_name} / {self.method_name}"
        return self.name


@dataclass
class FunctionNode:
    """A business-rule function."""

    name: str
    module: str
    docstring: str | None = None


@dataclass
class CallEdge:
    """A call from a function to a stub or another function."""

    caller: str  # function name
    caller_module: str
    callee: str  # dotted stub name (e.g. "CoreBanking.check_balance") or function name
    callee_module: str
    kind: str  # "service" or "function"


@dataclass
class DependencyGraph:
    """Complete dependency graph of a project's source directory."""

    services: dict[str, ServiceNode] = field(default_factory=dict)  # dotted key
    functions: dict[str, FunctionNode] = field(default_factory=dict)
    edges: list[CallEdge] = field(default_factory=list)

    # ----- Query helpers ----------------------------------------------------

    def edges_from(self, func_name: str) -> list[CallEdge]:
        """All direct calls made by *func_name*."""
        return [e for e in self.edges if e.caller == func_name]

    def edges_to(self, name: str) -> list[CallEdge]:
        """All callers of *name* (stub or function)."""
        return [e for e in self.edges if e.callee == name]

    def transitive_deps(self, func_name: str) -> set[str]:
        """All stubs and functions reachable from *func_name*."""
        visited: set[str] = set()
        stack = [func_name]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for edge in self.edges_from(current):
                stack.append(edge.callee)
        visited.discard(func_name)
        return visited

    def has_stub(self, class_name: str, method_name: str) -> bool:
        """Return True if ``ClassName.method_name`` is a known stub."""
        return f"{class_name}.{method_name}" in self.services

    # ----- Mermaid rendering ------------------------------------------------

    def to_mermaid(self, highlight_func: str | None = None) -> str:
        """Render the graph as a Mermaid flowchart."""
        if highlight_func:
            return self._mermaid_focused(highlight_func)
        return self._mermaid_full()

    def _mermaid_full(self) -> str:
        lines = ["graph LR"]
        for svc in self.services.values():
            label = svc.display_name
            lines.append(f'    {_mermaid_id(svc.name)}(["{label}"]):::service')
        for func in self.functions.values():
            lines.append(f'    {func.name}["{func.name}"]:::func')
        for edge in self.edges:
            if edge.kind == "service":
                method = edge.callee.split(".", 1)[-1]
                cid = _mermaid_id(edge.callee)
                lines.append(f"    {edge.caller} -->|.{method}| {cid}")
            else:
                lines.append(f"    {edge.caller} --> {edge.callee}")
        lines.append("")
        lines.append("    classDef service fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100")
        lines.append("    classDef func fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#1565c0")
        return "\n".join(lines)

    def _mermaid_focused(self, func_name: str) -> str:
        """Render only the subgraph reachable from *func_name*."""
        reachable = self.transitive_deps(func_name)
        reachable.add(func_name)

        relevant_edges = [
            e for e in self.edges
            if e.caller in reachable and e.callee in reachable
        ]

        lines = ["graph LR"]

        if func_name in self.functions:
            lines.append(f'    {func_name}["{func_name}"]:::entry')

        for name in sorted(reachable):
            if name == func_name:
                continue
            if name in self.services:
                label = self.services[name].display_name
                lines.append(f'    {_mermaid_id(name)}(["{label}"]):::service')
            elif name in self.functions:
                lines.append(f'    {name}["{name}"]:::func')

        for edge in relevant_edges:
            if edge.kind == "service":
                method = edge.callee.split(".", 1)[-1]
                cid = _mermaid_id(edge.callee)
                lines.append(f"    {edge.caller} -->|.{method}| {cid}")
            else:
                lines.append(f"    {edge.caller} --> {edge.callee}")

        lines.append("")
        lines.append("    classDef service fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100")
        lines.append("    classDef func fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#1565c0")
        lines.append("    classDef entry fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32")
        return "\n".join(lines)


def _mermaid_id(dotted: str) -> str:
    """Convert a dotted stub name into a Mermaid-safe identifier."""
    return dotted.replace(".", "__")


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------


def analyze_directory(src_dir: Path, project_root: Path) -> DependencyGraph:
    """Analyze all ``.py`` files under *src_dir* and return a dependency graph."""
    graph = DependencyGraph()
    py_files = sorted(src_dir.rglob("*.py"))

    # First pass: collect every @service entity, its @stub methods and every
    # top-level business-rule function.
    for py_file in py_files:
        rel = str(py_file.relative_to(project_root))
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        _collect_declarations(tree, rel, graph)

    # Second pass: walk function bodies and emit call edges.
    for py_file in py_files:
        rel = str(py_file.relative_to(project_root))
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        _collect_calls(tree, rel, graph)

    return graph


def analyze_file(py_file: Path, project_root: Path) -> DependencyGraph:
    """Analyze a single file. Also scans sibling files for declarations."""
    src_dir = py_file.parent
    return analyze_directory(src_dir, project_root)


# ---------------------------------------------------------------------------
# Decorator detection
# ---------------------------------------------------------------------------


def _decorator_name(dec: ast.expr) -> str | None:
    """Return the bare name of a decorator expression.

    Handles: ``@name``, ``@module.name``, ``@name(...)``, ``@module.name(...)``.
    """
    target: ast.expr = dec
    if isinstance(dec, ast.Call):
        target = dec.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _is_service_decorated(class_node: ast.ClassDef) -> bool:
    """Return True if *class_node* carries a ``@service`` decorator."""
    for dec in class_node.decorator_list:
        if _decorator_name(dec) == "service":
            return True
    return False


def _find_stub_decorator(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    """Return the ``@stub(...)`` decorator call node, or ``None`` if absent."""
    for dec in func_node.decorator_list:
        # @stub(...) — a Call expression
        if isinstance(dec, ast.Call) and _decorator_name(dec) == "stub":
            return dec
        # @stub  — bare name (no parens) is unusual but tolerated
        if isinstance(dec, (ast.Name, ast.Attribute)) and _decorator_name(dec) == "stub":
            return ast.Call(func=dec, args=[], keywords=[])
    return None


def _stub_kwarg(stub_call: ast.Call, name: str) -> ast.expr | None:
    """Return the AST value of ``@stub(..., {name}=...)`` or ``None``."""
    for kw in stub_call.keywords:
        if kw.arg == name:
            return kw.value
    return None


# ---------------------------------------------------------------------------
# First pass — declarations
# ---------------------------------------------------------------------------


def _collect_declarations(tree: ast.Module, module: str, graph: DependencyGraph) -> None:
    """Find @service classes, their @stub methods and top-level functions."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            if not _is_service_decorated(node):
                continue
            for member in node.body:
                if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                stub_call = _find_stub_decorator(member)
                if stub_call is None:
                    continue
                dotted = f"{node.name}.{member.name}"
                pydantic_class, pydantic_fields = _extract_pydantic_mock_info(
                    stub_call, tree,
                )
                graph.services[dotted] = ServiceNode(
                    name=dotted,
                    module=module,
                    docstring=ast.get_docstring(member),
                    mock_data_default=_extract_mock_default(stub_call),
                    component_name=node.name,
                    method_name=member.name,
                    mock_error_default=_extract_mock_error_default(stub_call),
                    mock_pydantic_fields=pydantic_fields,
                    mock_pydantic_class=pydantic_class,
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            graph.functions[node.name] = FunctionNode(
                name=node.name,
                module=module,
                docstring=ast.get_docstring(node),
            )


# ---------------------------------------------------------------------------
# Second pass — call edges
# ---------------------------------------------------------------------------


def _collect_calls(tree: ast.Module, module: str, graph: DependencyGraph) -> None:
    """Walk function bodies and find calls to stubs and other functions."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name not in graph.functions:
                continue
            _walk_body_for_calls(node, module, graph)


def _walk_body_for_calls(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    module: str,
    graph: DependencyGraph,
) -> None:
    """Inspect every call expression in a function body.

    Detects two patterns:

    * Direct: ``Entity().method(...)``
    * Aliased: ``e = Entity()`` followed by ``e.method(...)``
    """
    aliases = _collect_entity_aliases(func_node, graph)

    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue

        # Pattern: ServiceClass().method_name(...)  →  stub call
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            class_name = _extract_instantiation_name(node.func.value)
            # Aliased: receiver is a Name bound to a known entity instance.
            if class_name is None and isinstance(node.func.value, ast.Name):
                class_name = aliases.get(node.func.value.id)
            if class_name and graph.has_stub(class_name, method_name):
                dotted = f"{class_name}.{method_name}"
                graph.edges.append(CallEdge(
                    caller=func_node.name,
                    caller_module=module,
                    callee=dotted,
                    callee_module=graph.services[dotted].module,
                    kind="service",
                ))
                continue

        # Pattern: other_function(...)  →  function dependency
        callee_name = _extract_call_name(node)
        if callee_name and callee_name in graph.functions and callee_name != func_node.name:
            graph.edges.append(CallEdge(
                caller=func_node.name,
                caller_module=module,
                callee=callee_name,
                callee_module=graph.functions[callee_name].module,
                kind="function",
            ))


def _collect_entity_aliases(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    graph: DependencyGraph,
) -> dict[str, str]:
    """Build a map of local variables bound to service-entity instances.

    Detects assignments like ``bank = CoreBanking()`` and returns
    ``{"bank": "CoreBanking"}`` so call analysis can resolve
    ``bank.check_balance(...)`` as a call on ``CoreBanking``.

    Only top-level ``ast.Assign`` nodes within the function body are
    considered (no nested-scope tracking, no reassignment).
    """
    aliases: dict[str, str] = {}
    known_entities = {svc.split(".", 1)[0] for svc in graph.services}
    for stmt in ast.walk(func_node):
        if not isinstance(stmt, ast.Assign):
            continue
        if not isinstance(stmt.value, ast.Call):
            continue
        class_name = _extract_instantiation_name(stmt.value)
        if class_name not in known_entities:
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                aliases[target.id] = class_name  # type: ignore[assignment]
    return aliases


def _extract_instantiation_name(node: ast.expr) -> str | None:
    """Given ``ServiceClass()``, return ``"ServiceClass"``."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
    return None


def _extract_call_name(node: ast.Call) -> str | None:
    """Extract the simple function name from a call, e.g. ``func(...)``."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


# ---------------------------------------------------------------------------
# @stub kwarg extraction
# ---------------------------------------------------------------------------


def _extract_mock_default(stub_call: ast.Call) -> Any:
    """Return the literal value of ``@stub(mock=...)``, or ``None``."""
    expr = _stub_kwarg(stub_call, "mock")
    if expr is None:
        return None
    try:
        return ast.literal_eval(expr)
    except (ValueError, TypeError):
        return None


def _extract_mock_error_default(stub_call: ast.Call) -> dict[str, Any] | None:
    """Parse ``error=MockError(error_code=..., error_message=..., http_code=...)``.

    Both keyword and positional arguments to ``MockError`` are accepted
    (positional order: error_code, error_message, http_code).
    """
    expr = _stub_kwarg(stub_call, "error")
    if expr is None or not isinstance(expr, ast.Call):
        return None
    func = expr.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != "MockError":
        return None

    result: dict[str, Any] = {}
    positional = ("error_code", "error_message", "http_code")
    for i, arg in enumerate(expr.args):
        if i >= len(positional):
            break
        try:
            result[positional[i]] = ast.literal_eval(arg)
        except (ValueError, TypeError):
            pass
    for kw in expr.keywords:
        if kw.arg in positional:
            try:
                result[kw.arg] = ast.literal_eval(kw.value)
            except (ValueError, TypeError):
                pass
    if "error_code" in result and "error_message" in result:
        return result
    return None


def _extract_pydantic_mock_info(
    stub_call: ast.Call,
    module_tree: ast.Module,
) -> tuple[str | None, list[PydanticFieldInfo] | None]:
    """Detect ``mock=ModelClass(...)`` and extract Pydantic field schema."""
    expr = _stub_kwarg(stub_call, "mock")
    if expr is None or not isinstance(expr, ast.Call):
        return None, None

    call_func = expr.func
    model_name: str | None = None
    if isinstance(call_func, ast.Name):
        model_name = call_func.id
    elif isinstance(call_func, ast.Attribute):
        model_name = call_func.attr
    if model_name is None:
        return None, None

    model_class = _find_class_in_module(model_name, module_tree)
    if model_class is None:
        return None, None
    if not _is_pydantic_model(model_class):
        return None, None

    fields = _extract_pydantic_fields(model_class)
    call_defaults = _extract_call_kwargs(expr)
    for f in fields:
        if f.name in call_defaults and f.default is None:
            f.default = call_defaults[f.name]

    return model_name, fields


def _find_class_in_module(class_name: str, tree: ast.Module) -> ast.ClassDef | None:
    """Find a class definition by name in the module AST."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


_PYDANTIC_BASES = {"BaseModel"}


def _is_pydantic_model(class_node: ast.ClassDef) -> bool:
    """Check if the class inherits from ``BaseModel`` (Pydantic)."""
    for base in class_node.bases:
        if isinstance(base, ast.Name) and base.id in _PYDANTIC_BASES:
            return True
        if isinstance(base, ast.Attribute) and base.attr in _PYDANTIC_BASES:
            return True
    return False


def _extract_pydantic_fields(class_node: ast.ClassDef) -> list[PydanticFieldInfo]:
    """Extract annotated fields from a Pydantic model class definition."""
    fields: list[PydanticFieldInfo] = []
    for item in class_node.body:
        if not isinstance(item, ast.AnnAssign):
            continue
        if not isinstance(item.target, ast.Name):
            continue
        name = item.target.id
        if name.startswith("_"):
            continue
        annotation = ast.unparse(item.annotation) if item.annotation else "str"
        for prefix in ("builtins.", "typing."):
            if annotation.startswith(prefix):
                annotation = annotation[len(prefix):]
        default = None
        if item.value is not None:
            try:
                default = ast.literal_eval(item.value)
            except (ValueError, TypeError):
                pass
        fields.append(PydanticFieldInfo(name=name, annotation=annotation, default=default))
    return fields


def _extract_call_kwargs(call_node: ast.Call) -> dict[str, Any]:
    """Extract keyword arguments from a constructor call as literal values."""
    result: dict[str, Any] = {}
    for kw in call_node.keywords:
        if kw.arg is None:
            continue
        try:
            result[kw.arg] = ast.literal_eval(kw.value)
        except (ValueError, TypeError):
            pass
    return result


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------


def get_service_mock_defaults(
    graph: DependencyGraph,
    func_name: str,
) -> list[dict[str, Any]]:
    """Return mock default info for all stubs reachable from *func_name*.

    Each entry is a dict with ``name`` (dotted), ``method_name``,
    ``component_name``, ``display_name``, ``docstring``, ``default_json``,
    ``error_default``, and ``pydantic_fields``.
    """
    deps = graph.transitive_deps(func_name)
    results: list[dict[str, Any]] = []
    for dep_name in sorted(deps):
        if dep_name not in graph.services:
            continue
        svc = graph.services[dep_name]
        try:
            default_json = json.dumps(svc.mock_data_default, ensure_ascii=False)
        except (TypeError, ValueError):
            default_json = "null"
        pydantic_fields_info = None
        if svc.mock_pydantic_fields:
            pydantic_fields_info = [
                {"name": f.name, "annotation": f.annotation, "default": f.default}
                for f in svc.mock_pydantic_fields
            ]
        results.append({
            "name": svc.name,  # dotted "ClassName.method_name"
            "method_name": svc.method_name,
            "component_name": svc.component_name,
            "display_name": svc.display_name,
            "docstring": svc.docstring,
            "default_json": default_json,
            "error_default": svc.mock_error_default,
            "pydantic_fields": pydantic_fields_info,
            "pydantic_class": svc.mock_pydantic_class,
        })
    return results
