"""Static dependency analyzer for Speks projects.

Walks Python source files and builds a graph of:
- **ExternalService subclasses** (blackbox services)
- **Business-rule functions** and which services / other functions they call
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
    """An ExternalService subclass (blackbox)."""

    name: str
    module: str  # relative file path, e.g. "src/regles.py"
    docstring: str | None = None
    mock_data_default: Any = None  # default value returned by mock()
    component_name: str | None = None  # logical grouping (e.g. "CoreBanking")
    mock_error_default: dict[str, Any] | None = None  # default error from mock_error()
    mock_pydantic_fields: list[PydanticFieldInfo] | None = None  # Pydantic model fields
    mock_pydantic_class: str | None = None  # Pydantic model class name

    @property
    def display_name(self) -> str:
        """Return ``ComponentName / ServiceName`` when a component is set."""
        if self.component_name:
            return f"{self.component_name} / {self.name}"
        return self.name


@dataclass
class FunctionNode:
    """A business-rule function."""

    name: str
    module: str
    docstring: str | None = None


@dataclass
class CallEdge:
    """A call from a function to a service or another function."""

    caller: str  # function name
    caller_module: str
    callee: str  # service class name or function name
    callee_module: str
    kind: str  # "service" or "function"


@dataclass
class DependencyGraph:
    """Complete dependency graph of a project's source directory."""

    services: dict[str, ServiceNode] = field(default_factory=dict)
    functions: dict[str, FunctionNode] = field(default_factory=dict)
    edges: list[CallEdge] = field(default_factory=list)

    # ----- Query helpers ----------------------------------------------------

    def edges_from(self, func_name: str) -> list[CallEdge]:
        """All direct calls made by *func_name*."""
        return [e for e in self.edges if e.caller == func_name]

    def edges_to(self, name: str) -> list[CallEdge]:
        """All callers of *name* (service or function)."""
        return [e for e in self.edges if e.callee == name]

    def transitive_deps(self, func_name: str) -> set[str]:
        """All services and functions reachable from *func_name*."""
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

    # ----- Mermaid rendering ------------------------------------------------

    def to_mermaid(self, highlight_func: str | None = None) -> str:
        """Render the graph as a Mermaid flowchart.

        Parameters
        ----------
        highlight_func:
            If given, only show the subgraph reachable from this function
            and apply special styling to highlight the call chain.
        """
        if highlight_func:
            return self._mermaid_focused(highlight_func)
        return self._mermaid_full()

    def _mermaid_full(self) -> str:
        lines = ["graph LR"]
        # Declare service nodes (stadium shape)
        for svc in self.services.values():
            label = svc.display_name
            lines.append(f'    {svc.name}(["{label}"]):::service')
        # Declare function nodes (rounded rectangle)
        for func in self.functions.values():
            label = f"{func.name}"
            lines.append(f'    {func.name}["{label}"]:::func')
        # Edges
        for edge in self.edges:
            if edge.kind == "service":
                lines.append(f"    {edge.caller} -->|.call| {edge.callee}")
            else:
                lines.append(f"    {edge.caller} --> {edge.callee}")
        # Styles
        lines.append("")
        lines.append("    classDef service fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100")
        lines.append("    classDef func fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#1565c0")
        return "\n".join(lines)

    def _mermaid_focused(self, func_name: str) -> str:
        """Render only the subgraph reachable from *func_name*."""
        reachable = self.transitive_deps(func_name)
        reachable.add(func_name)

        # Collect relevant edges
        relevant_edges = [
            e for e in self.edges
            if e.caller in reachable and e.callee in reachable
        ]

        lines = ["graph LR"]

        # Entry function
        if func_name in self.functions:
            lines.append(f'    {func_name}["{func_name}"]:::entry')

        # Nodes
        for name in sorted(reachable):
            if name == func_name:
                continue
            if name in self.services:
                label = self.services[name].display_name
                lines.append(f'    {name}(["{label}"]):::service')
            elif name in self.functions:
                lines.append(f'    {name}["{name}"]:::func')

        # Edges
        for edge in relevant_edges:
            if edge.kind == "service":
                lines.append(f"    {edge.caller} -->|.call| {edge.callee}")
            else:
                lines.append(f"    {edge.caller} --> {edge.callee}")

        # Styles
        lines.append("")
        lines.append("    classDef service fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100")
        lines.append("    classDef func fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#1565c0")
        lines.append("    classDef entry fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px,color:#2e7d32")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------


def analyze_directory(src_dir: Path, project_root: Path) -> DependencyGraph:
    """Analyze all ``.py`` files under *src_dir* and return a dependency graph."""
    graph = DependencyGraph()
    py_files = sorted(src_dir.rglob("*.py"))

    # First pass: collect all ExternalService subclasses and functions
    for py_file in py_files:
        rel = str(py_file.relative_to(project_root))
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        _collect_declarations(tree, rel, graph)

    # Second pass: analyze function bodies for calls
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
    """Analyze a single file. Also scans sibling files for service/function declarations."""
    src_dir = py_file.parent
    return analyze_directory(src_dir, project_root)


# ---------------------------------------------------------------------------
# Internals — first pass (declarations)
# ---------------------------------------------------------------------------

_EXTERNAL_SERVICE_BASES = {"ExternalService"}


def _collect_declarations(tree: ast.Module, module: str, graph: DependencyGraph) -> None:
    """Find ExternalService subclasses and top-level functions."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            if _is_service_subclass(node):
                pydantic_class, pydantic_fields = _extract_pydantic_mock_info(
                    node, tree
                )
                graph.services[node.name] = ServiceNode(
                    name=node.name,
                    module=module,
                    docstring=ast.get_docstring(node),
                    mock_data_default=_extract_mock_default(node),
                    component_name=_extract_class_var(node, "component_name"),
                    mock_error_default=_extract_mock_error_default(node),
                    mock_pydantic_fields=pydantic_fields,
                    mock_pydantic_class=pydantic_class,
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            graph.functions[node.name] = FunctionNode(
                name=node.name,
                module=module,
                docstring=ast.get_docstring(node),
            )


def _is_service_subclass(node: ast.ClassDef) -> bool:
    """Check if any base class name matches known ExternalService bases."""
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in _EXTERNAL_SERVICE_BASES:
            return True
        if isinstance(base, ast.Attribute) and base.attr in _EXTERNAL_SERVICE_BASES:
            return True
    return False


# ---------------------------------------------------------------------------
# Internals — second pass (call edges)
# ---------------------------------------------------------------------------


def _collect_calls(tree: ast.Module, module: str, graph: DependencyGraph) -> None:
    """Walk function bodies and find calls to services and other functions."""
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
    """Inspect every call expression in a function body."""
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue

        # Pattern: ServiceClass().call(...)  →  service dependency
        if isinstance(node.func, ast.Attribute) and node.func.attr == "call":
            svc_name = _extract_instantiation_name(node.func.value)
            if svc_name and svc_name in graph.services:
                graph.edges.append(CallEdge(
                    caller=func_node.name,
                    caller_module=module,
                    callee=svc_name,
                    callee_module=graph.services[svc_name].module,
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
# Mock default extraction
# ---------------------------------------------------------------------------


def _extract_mock_default(class_node: ast.ClassDef) -> Any:
    """Extract the ``data`` value from ``MockResponse(data=...)`` in the ``mock()`` method.

    Returns *None* if the default cannot be determined statically.
    """
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "mock":
            for node in ast.walk(item):
                if not isinstance(node, ast.Return) or node.value is None:
                    continue
                data_expr = _find_mock_response_data(node.value)
                if data_expr is not None:
                    try:
                        return ast.literal_eval(data_expr)
                    except (ValueError, TypeError):
                        return None
    return None


def _find_mock_response_data(node: ast.expr) -> ast.expr | None:
    """Given a return-value expression, find the ``data=`` keyword in a MockResponse call."""
    if not isinstance(node, ast.Call):
        return None
    # Match MockResponse(...) by name
    func = node.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != "MockResponse":
        return None

    # Look for data= keyword
    for kw in node.keywords:
        if kw.arg == "data":
            return kw.value
    # If no keyword, first positional arg is data
    if node.args:
        return node.args[0]
    return None


def _extract_class_var(class_node: ast.ClassDef, var_name: str) -> str | None:
    """Extract a simple string class variable (e.g. ``component_name = "X"``)."""
    for item in class_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    try:
                        value = ast.literal_eval(item.value)
                        if isinstance(value, str):
                            return value
                    except (ValueError, TypeError):
                        pass
        elif isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name) and item.target.id == var_name and item.value:
                try:
                    value = ast.literal_eval(item.value)
                    if isinstance(value, str):
                        return value
                except (ValueError, TypeError):
                    pass
    return None


def _extract_mock_error_default(class_node: ast.ClassDef) -> dict[str, Any] | None:
    """Extract the default error from the ``mock_error()`` method.

    Looks for ``return MockErrorResponse(error_code=..., error_message=..., http_code=...)``
    and returns a dict with those keys, or ``None`` if not found.
    """
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "mock_error":
            for node in ast.walk(item):
                if not isinstance(node, ast.Return) or node.value is None:
                    continue
                result = _parse_mock_error_response(node.value)
                if result is not None:
                    return result
    return None


def _parse_mock_error_response(node: ast.expr) -> dict[str, Any] | None:
    """Parse a ``MockErrorResponse(...)`` call and return its fields as a dict."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != "MockErrorResponse":
        return None

    result: dict[str, Any] = {}
    # keyword arguments
    for kw in node.keywords:
        if kw.arg in ("error_code", "error_message", "http_code"):
            try:
                result[kw.arg] = ast.literal_eval(kw.value)
            except (ValueError, TypeError):
                pass
    # Need at least error_code and error_message
    if "error_code" in result and "error_message" in result:
        return result
    return None


def _extract_pydantic_mock_info(
    class_node: ast.ClassDef,
    module_tree: ast.Module,
) -> tuple[str | None, list[PydanticFieldInfo] | None]:
    """Detect Pydantic model usage in ``MockResponse(data=Model(...))`` and extract fields.

    Returns ``(class_name, fields)`` or ``(None, None)`` if mock data is not
    a Pydantic model constructor call.
    """
    # Step 1: find MockResponse(data=SomeClass(...)) in the mock() method
    for item in class_node.body:
        if not (isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "mock"):
            continue
        for node in ast.walk(item):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            data_expr = _find_mock_response_data(node.value)
            if data_expr is None or not isinstance(data_expr, ast.Call):
                continue
            # data=SomeClass(...)
            call_func = data_expr.func
            model_name: str | None = None
            if isinstance(call_func, ast.Name):
                model_name = call_func.id
            elif isinstance(call_func, ast.Attribute):
                model_name = call_func.attr
            if model_name is None:
                continue

            # Step 2: find the class definition in the same module
            model_class = _find_class_in_module(model_name, module_tree)
            if model_class is None:
                continue

            # Step 3: check if it inherits from BaseModel
            if not _is_pydantic_model(model_class):
                continue

            # Step 4: extract field definitions from the class
            fields = _extract_pydantic_fields(model_class)

            # Step 5: fill in defaults from the constructor call
            call_defaults = _extract_call_kwargs(data_expr)
            for f in fields:
                if f.name in call_defaults and f.default is None:
                    f.default = call_defaults[f.name]

            return model_name, fields

    return None, None


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
        # Skip private/dunder fields
        if name.startswith("_"):
            continue
        # Get annotation as string
        annotation = ast.unparse(item.annotation) if item.annotation else "str"
        # Simplify common types
        for prefix in ("builtins.", "typing."):
            if annotation.startswith(prefix):
                annotation = annotation[len(prefix):]
        # Get default value if present
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


def get_service_mock_defaults(
    graph: DependencyGraph,
    func_name: str,
) -> list[dict[str, Any]]:
    """Return mock default info for all services reachable from *func_name*.

    Each entry is a dict with ``name``, ``docstring``, ``default_json``
    (JSON-encoded default value), ``component_name``, and ``error_default``
    (dict or ``None``).
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
            "name": svc.name,
            "docstring": svc.docstring,
            "default_json": default_json,
            "component_name": svc.component_name,
            "display_name": svc.display_name,
            "error_default": svc.mock_error_default,
            "pydantic_fields": pydantic_fields_info,
            "pydantic_class": svc.mock_pydantic_class,
        })
    return results
