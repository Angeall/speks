"""Extract functions, classes, and docstrings from Python source files."""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FieldInfo:
    """Metadata about a field in a structured type (Pydantic model / dataclass)."""

    name: str
    annotation: str | None
    default: str | None
    required: bool
    comment: str | None = None


@dataclass
class StructuredTypeInfo:
    """Metadata about a Pydantic model or dataclass."""

    name: str
    fields: list[FieldInfo]
    docstring: str | None
    base_classes: list[str]


@dataclass
class FunctionInfo:
    """Metadata about an extracted Python function."""

    name: str
    source: str
    docstring: str | None
    parameters: list[ParameterInfo]
    return_annotation: str | None
    lineno: int
    return_description: str | None = None


@dataclass
class ParameterInfo:
    """Metadata about a function parameter."""

    name: str
    annotation: str | None
    default: str | None
    description: str | None = None


def parse_tag_arg(arg: str) -> tuple[str, str | None, str]:
    """Parse a tag argument into ``(file_part, class_name, symbol)``.

    Supported formats::

        src/file.py:func_name         → ("src/file.py", None, "func_name")
        src/file.py:Class:method      → ("src/file.py", "Class", "method")
        src/file.py                   → ("src/file.py", None, "")

    The file part is identified as the portion ending with ``.py``.
    """
    parts = arg.split(":")
    # Find the boundary: the file part ends with .py
    file_idx = -1
    for i, p in enumerate(parts):
        if p.endswith(".py"):
            file_idx = i
            break
    if file_idx == -1:
        # No .py found — treat entire arg as file path (or directory)
        return arg, None, ""

    file_part = ":".join(parts[: file_idx + 1])
    rest = parts[file_idx + 1 :]

    if len(rest) == 0:
        return file_part, None, ""
    elif len(rest) == 1:
        return file_part, None, rest[0]
    else:
        # rest[0] = class name, rest[1] = method name
        return file_part, rest[0], rest[1]


def _annotation_to_str(node: ast.expr | None) -> str | None:
    """Best-effort conversion of an AST annotation node to a string."""
    if node is None:
        return None
    return ast.unparse(node)


def _default_to_str(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    return ast.unparse(node)


def _extract_parameters(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ParameterInfo]:
    """Return parameter info for a function, excluding *self*."""
    params: list[ParameterInfo] = []
    args = func_node.args

    # Positional / normal args
    n_defaults = len(args.defaults)
    n_args = len(args.args)
    for i, arg in enumerate(args.args):
        if arg.arg == "self":
            continue
        default_index = i - (n_args - n_defaults)
        default = _default_to_str(args.defaults[default_index]) if default_index >= 0 else None
        params.append(ParameterInfo(
            name=arg.arg,
            annotation=_annotation_to_str(arg.annotation),
            default=default,
        ))

    # keyword-only
    for i, arg in enumerate(args.kwonlyargs):
        default = _default_to_str(args.kw_defaults[i]) if args.kw_defaults[i] else None
        params.append(ParameterInfo(
            name=arg.arg,
            annotation=_annotation_to_str(arg.annotation),
            default=default,
        ))

    return params


_PARAM_RE = re.compile(r"^:param\s+(\w+)\s*:\s*(.+)")
_RETURN_RE = re.compile(r"^:returns?\s*:\s*(.+)")


def _parse_docstring(docstring: str | None) -> tuple[str | None, dict[str, str], str | None]:
    """Parse a docstring and extract ``:param name: desc`` / ``:return: desc``.

    Returns ``(clean_docstring, param_descriptions, return_description)``.
    The clean docstring has all ``:param`` and ``:return`` lines removed.
    """
    if not docstring:
        return docstring, {}, None

    params: dict[str, str] = {}
    return_desc: str | None = None
    clean_lines: list[str] = []

    for line in docstring.splitlines():
        stripped = line.strip()
        m_param = _PARAM_RE.match(stripped)
        if m_param:
            params[m_param.group(1)] = m_param.group(2).strip()
            continue
        m_ret = _RETURN_RE.match(stripped)
        if m_ret:
            return_desc = m_ret.group(1).strip()
            continue
        clean_lines.append(line)

    # Strip trailing blank lines from clean docstring
    while clean_lines and not clean_lines[-1].strip():
        clean_lines.pop()

    clean = "\n".join(clean_lines).strip() or None
    return clean, params, return_desc


def extract_function(
    source_path: Path, function_name: str, *, class_name: str | None = None,
) -> FunctionInfo:
    """Extract a function (or method) by name.

    When *class_name* is given, look for a method inside that class instead
    of a module-level function.

    Raises ``ValueError`` if the function is not found.
    """
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(source_path))

    search_nodes: list[ast.AST]
    if class_name is not None:
        # Find the class first, then search methods inside it
        cls_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                cls_node = node
                break
        if cls_node is None:
            raise ValueError(f"Class '{class_name}' not found in {source_path}")
        search_nodes = list(ast.iter_child_nodes(cls_node))
    else:
        search_nodes = list(ast.walk(tree))

    for node in search_nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            source_lines = source_text.splitlines()
            # node.end_lineno is 1-indexed inclusive
            end = node.end_lineno or node.lineno
            func_source = "\n".join(source_lines[node.lineno - 1 : end])
            raw_docstring = ast.get_docstring(node)
            clean_doc, param_descs, return_desc = _parse_docstring(raw_docstring)
            params = _extract_parameters(node)
            for p in params:
                if p.name in param_descs:
                    p.description = param_descs[p.name]
            return FunctionInfo(
                name=node.name,
                source=func_source,
                docstring=clean_doc,
                parameters=params,
                return_annotation=_annotation_to_str(node.returns),
                lineno=node.lineno,
                return_description=return_desc,
            )

    if class_name:
        raise ValueError(f"Method '{function_name}' not found in class '{class_name}' in {source_path}")
    raise ValueError(f"Function '{function_name}' not found in {source_path}")


def extract_class(source_path: Path, class_name: str) -> str:
    """Extract the full source of a class by name."""
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(source_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            source_lines = source_text.splitlines()
            end = node.end_lineno or node.lineno
            return "\n".join(source_lines[node.lineno - 1 : end])

    raise ValueError(f"Class '{class_name}' not found in {source_path}")


_STRUCTURED_BASES = {
    "BaseModel", "BaseSettings",  # Pydantic
    "TypedDict",  # typing
}


def _is_structured_class(node: ast.ClassDef) -> bool:
    """Return True if the class looks like a Pydantic model, dataclass, or TypedDict."""
    for base in node.bases:
        name = ast.unparse(base)
        # Handle both ``BaseModel`` and ``pydantic.BaseModel``
        short = name.rsplit(".", 1)[-1]
        if short in _STRUCTURED_BASES:
            return True
    for deco in node.decorator_list:
        deco_str = ast.unparse(deco)
        if "dataclass" in deco_str:
            return True
    return False


def _extract_class_fields(node: ast.ClassDef, source_lines: list[str]) -> list[FieldInfo]:
    """Extract typed fields from a class body (Pydantic, dataclass, TypedDict)."""
    fields: list[FieldInfo] = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            annotation = _annotation_to_str(stmt.annotation)
            default = _default_to_str(stmt.value) if stmt.value else None
            # A field is optional if it has a default or if wrapped in Optional
            required = default is None and not (annotation or "").startswith("Optional")
            # Extract inline comment from the source line
            comment = _extract_inline_comment(stmt, source_lines)
            fields.append(FieldInfo(
                name=name,
                annotation=annotation,
                default=default,
                required=required,
                comment=comment,
            ))
    return fields


def _extract_inline_comment(node: ast.AST, source_lines: list[str]) -> str | None:
    """Extract a ``# comment`` from the end of the source line for an AST node."""
    lineno = getattr(node, "lineno", None)
    if lineno is None or lineno < 1 or lineno > len(source_lines):
        return None
    line = source_lines[lineno - 1]
    # Find '#' that is not inside a string
    in_str: str | None = None
    for i, ch in enumerate(line):
        if in_str:
            if ch == in_str and (i == 0 or line[i - 1] != "\\"):
                in_str = None
        elif ch in ('"', "'"):
            in_str = ch
        elif ch == "#":
            comment = line[i + 1:].strip()
            return comment if comment else None
    return None


def extract_structured_types(source_path: Path) -> dict[str, StructuredTypeInfo]:
    """Extract all structured types (Pydantic models, dataclasses, TypedDicts) from a file.

    Returns a dict mapping class name → StructuredTypeInfo.
    """
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(source_path))

    source_lines = source_text.splitlines()
    result: dict[str, StructuredTypeInfo] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_structured_class(node):
            fields = _extract_class_fields(node, source_lines)
            if fields:
                base_names = [ast.unparse(b) for b in node.bases]
                result[node.name] = StructuredTypeInfo(
                    name=node.name,
                    fields=fields,
                    docstring=ast.get_docstring(node),
                    base_classes=base_names,
                )
    return result


def extract_all_functions(source_path: Path) -> list[FunctionInfo]:
    """Extract all top-level functions from a Python file."""
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(source_path))
    source_lines = source_text.splitlines()

    results: list[FunctionInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            func_source = "\n".join(source_lines[node.lineno - 1 : end])
            results.append(FunctionInfo(
                name=node.name,
                source=func_source,
                docstring=ast.get_docstring(node),
                parameters=_extract_parameters(node),
                return_annotation=_annotation_to_str(node.returns),
                lineno=node.lineno,
            ))
    return results
