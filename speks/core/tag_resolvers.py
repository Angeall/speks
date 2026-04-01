"""Shared tag resolvers for all Speks consumers.

Every ``@[kind](arg)`` tag is resolved by one function here.  The three
consumers (core parser, MkDocs plugin, standalone renderer) all call into
this module so that the resolution logic lives in exactly one place.

The *mode* parameter controls output variants:

* ``"markdown"`` — emit Markdown (fenced blocks, Markdown tables).
  Used by the core parser.
* ``"mkdocs"`` — emit HTML widgets ready for MkDocs Material.  The
  playground is fully interactive (``onclick`` handler).
* ``"standalone"`` — emit HTML widgets for the IDE preview.  The
  playground button is disabled (no server).
"""

from __future__ import annotations

import html as html_mod
import re
from pathlib import Path
from typing import Literal

from speks.core.code_extractor import (
    StructuredTypeInfo,
    extract_class,
    extract_function,
    extract_structured_types,
    parse_tag_arg,
)
from speks.core.testcases import load_testcases
from speks.i18n import t

# ---------------------------------------------------------------------------
# Tag regex  — matches  @[kind](argument)
# ---------------------------------------------------------------------------

TAG_RE = re.compile(
    r"@\[(?P<kind>code|plantuml|mermaid|playground|contract)\]\((?P<arg>[^)]+)\)"
)

Mode = Literal["markdown", "mkdocs", "standalone"]

# ---------------------------------------------------------------------------
# code
# ---------------------------------------------------------------------------


def resolve_code(arg: str, root: Path) -> str:
    """``@[code](file.py:symbol)`` or ``@[code](file.py:Class:method)``."""
    file_part, class_name, symbol = parse_tag_arg(arg)

    file_path = root / file_part
    if not file_path.exists():
        return f"<!-- speks: file not found: {file_part} -->"

    if symbol:
        try:
            info = extract_function(file_path, symbol, class_name=class_name)
            code = info.source
        except ValueError:
            if class_name is None:
                try:
                    code = extract_class(file_path, symbol)
                except ValueError:
                    return f"<!-- speks: symbol '{symbol}' not found in {file_part} -->"
            else:
                return f"<!-- speks: method '{class_name}:{symbol}' not found in {file_part} -->"
    elif class_name:
        # @[code](file.py:ClassName) — extract the whole class
        try:
            code = extract_class(file_path, class_name)
        except ValueError:
            return f"<!-- speks: class '{class_name}' not found in {file_part} -->"
    else:
        code = file_path.read_text(encoding="utf-8")

    return f"```python\n{code}\n```"


# ---------------------------------------------------------------------------
# plantuml
# ---------------------------------------------------------------------------


def resolve_plantuml(arg: str, root: Path, *, mode: Mode = "mkdocs") -> str:
    """``@[plantuml](diagrams/seq.puml)``."""
    file_path = root / arg
    if not file_path.exists():
        if mode == "standalone":
            return f'<div class="speks-diagram-placeholder">{t("plantuml.file_not_found", arg=arg)}</div>'
        return f"<!-- speks: diagram not found: {arg} -->"

    if mode == "standalone":
        return f'<div class="speks-diagram-placeholder">PlantUML: {arg}</div>'

    content = file_path.read_text(encoding="utf-8")
    return f"```plantuml\n{content}\n```"


# ---------------------------------------------------------------------------
# mermaid
# ---------------------------------------------------------------------------


def resolve_mermaid(arg: str, root: Path) -> str:
    """``@[mermaid](diagrams/flow.mmd)`` → fenced mermaid block."""
    file_path = root / arg
    if not file_path.exists():
        return f"<!-- speks: diagram not found: {arg} -->"

    content = file_path.read_text(encoding="utf-8")
    return f"```mermaid\n{content}\n```"


# ---------------------------------------------------------------------------
# contract
# ---------------------------------------------------------------------------


def _collect_structured_types(file_path: Path, root: Path) -> dict[str, StructuredTypeInfo]:
    """Collect structured types from the source file and its src/ siblings."""
    types: dict[str, StructuredTypeInfo] = {}
    try:
        types.update(extract_structured_types(file_path))
    except Exception:
        pass
    # Also scan sibling .py files in the same directory
    for sibling in file_path.parent.glob("*.py"):
        if sibling != file_path:
            try:
                types.update(extract_structured_types(sibling))
            except Exception:
                pass
    return types


def resolve_contract(arg: str, root: Path, *, mode: Mode = "mkdocs") -> str:
    """``@[contract](file.py:func)`` or ``@[contract](file.py:Class:method)``."""
    file_part, class_name, func_name = parse_tag_arg(arg)
    if not func_name:
        return "<!-- speks: contract tag requires file:function format -->"

    file_path = root / file_part
    if not file_path.exists():
        return f"<!-- speks: file not found: {file_part} -->"

    try:
        info = extract_function(file_path, func_name, class_name=class_name)
    except ValueError:
        label = f"{class_name}:{func_name}" if class_name else func_name
        return f"<!-- speks: function '{label}' not found in {file_part} -->"

    structured_types = _collect_structured_types(file_path, root)
    display_name = f"{class_name}.{func_name}" if class_name else func_name

    if mode == "markdown":
        return _contract_markdown(info, display_name)
    return _contract_html(info, display_name, structured_types=structured_types)


def _contract_markdown(info: object, func_name: str) -> str:
    """Markdown-table variant (used by the core parser)."""
    rows = ""
    for p in info.parameters:  # type: ignore[attr-defined]
        ann = p.annotation or "—"
        default = p.default or "—"
        desc = p.description or "—"
        rows += f"| `{p.name}` | `{ann}` | {default} | {desc} |\n"

    if not rows:
        rows = "| — | — | — | — |\n"

    ret = info.return_annotation or "—"  # type: ignore[attr-defined]
    ret_desc = info.return_description or ""  # type: ignore[attr-defined]
    ret_suffix = f" — {ret_desc}" if ret_desc else ""

    return (
        f"**`{func_name}`**\n\n"
        f"| {t('contract.parameter')} | {t('contract.type')} | {t('contract.default')} | {t('contract.description')} |\n"
        f"|-----------|------|--------|-------------|\n"
        f"{rows}\n"
        f"**{t('contract.return')}** : `{ret}`{ret_suffix}\n"
    )


def _strip_generic_wrapper(type_str: str) -> str | None:
    """Extract the inner type name from ``list[X]``, ``Optional[X]``, ``X | None``, etc.

    Recursively strips wrappers so that ``Optional[list[X]]`` yields ``X``.
    Returns the bare type name, or ``None`` for empty input.
    """
    if not type_str:
        return None
    inner = type_str.strip()

    # Handle PEP 604 union: ``X | None``, ``None | X``, ``X | Y`` (take first non-None)
    if " | " in inner:
        parts = [p.strip() for p in inner.split(" | ")]
        non_none = [p for p in parts if p != "None"]
        if non_none:
            inner = non_none[0]
        else:
            return inner

    # Handle Union[X, None], Union[X, Y] — take first non-None member
    for union_prefix in ("Union[", "typing.Union["):
        if inner.startswith(union_prefix) and inner.endswith("]"):
            body = inner[len(union_prefix):-1]
            parts = [p.strip() for p in body.split(",")]
            non_none = [p for p in parts if p != "None"]
            if non_none:
                inner = non_none[0]
            break

    # Repeatedly strip container wrappers: Optional[list[X]] → list[X] → X
    _WRAPPERS = ("Optional[", "list[", "List[", "Sequence[", "Set[", "set[", "tuple[", "Tuple[", "frozenset[", "FrozenSet[")
    changed = True
    while changed:
        changed = False
        for wrapper in _WRAPPERS:
            if inner.startswith(wrapper) and inner.endswith("]"):
                inner = inner[len(wrapper):-1]
                # For tuple[X, ...] strip the trailing ", ..."
                if inner.endswith(", ..."):
                    inner = inner[:-5]
                changed = True
                break

    # Handle dict value: dict[str, X] → X
    if inner.startswith(("dict[", "Dict[")):
        parts = inner.split(",", 1)
        if len(parts) == 2:
            inner = parts[1].strip().rstrip("]")

    return inner


def _type_detail_html(
    type_str: str,
    structured_types: dict[str, StructuredTypeInfo],
    seen: set[str] | None = None,
) -> str:
    """Render a collapsible type detail if *type_str* references a structured type."""
    if not type_str or not structured_types:
        return ""
    if seen is None:
        seen = set()

    # Try to find the type — could be bare name or wrapped in Optional/list/etc.
    candidates = [type_str]
    inner = _strip_generic_wrapper(type_str)
    if inner and inner != type_str:
        candidates.append(inner)

    type_info: StructuredTypeInfo | None = None
    for candidate in candidates:
        # Match by short name (ignore module prefix)
        short = candidate.rsplit(".", 1)[-1]
        if short in structured_types:
            type_info = structured_types[short]
            break

    if type_info is None or type_info.name in seen:
        return ""

    seen.add(type_info.name)

    field_rows = ""
    for f in type_info.fields:
        f_name = html_mod.escape(f.name)
        f_ann = html_mod.escape(f.annotation or "—")
        f_default = html_mod.escape(f.default) if f.default else "—"
        req_mark = ' <span class="speks-required">*</span>' if f.required else ""
        comment_html = ""
        if f.comment:
            comment_html = f' <em class="speks-contract-field-comment">{html_mod.escape(f.comment)}</em>'
        nested = _type_detail_html(f.annotation or "", structured_types, seen)
        field_rows += (
            f"          <tr>"
            f"<td><code>{f_name}</code>{req_mark}{comment_html}</td>"
            f"<td><code>{f_ann}</code></td>"
            f"<td>{f_default}</td>"
            f"</tr>\n"
        )
        if nested:
            field_rows += (
                f'          <tr><td colspan="3" class="speks-contract-nested">{nested}</td></tr>\n'
            )

    doc = ""
    if type_info.docstring:
        doc = f'<em class="speks-contract-type-doc">{html_mod.escape(type_info.docstring)}</em>'

    return (
        f'<details class="speks-contract-type-details">\n'
        f"        <summary>"
        f"<code>{html_mod.escape(type_info.name)}</code> {doc}</summary>\n"
        f'        <table class="speks-contract-table speks-contract-nested-table">\n'
        f"          <thead><tr>"
        f"<th>{t('contract.parameter')}</th>"
        f"<th>{t('contract.type')}</th>"
        f"<th>{t('contract.default')}</th>"
        f"</tr></thead>\n"
        f"          <tbody>\n{field_rows}          </tbody>\n"
        f"        </table>\n"
        f"      </details>"
    )


def _contract_html(
    info: object,
    func_name: str,
    *,
    structured_types: dict[str, StructuredTypeInfo] | None = None,
) -> str:
    """HTML-table variant (MkDocs and standalone)."""
    stypes = structured_types or {}
    ncols = 4
    input_rows = ""
    for p in info.parameters:  # type: ignore[attr-defined]
        name = html_mod.escape(p.name)
        ann = html_mod.escape(p.annotation or "—")
        default = html_mod.escape(p.default) if p.default else "—"
        desc = html_mod.escape(p.description) if p.description else "—"
        input_rows += (
            f"      <tr>"
            f"<td><code>{name}</code></td>"
            f"<td><code>{ann}</code></td>"
            f"<td>{default}</td>"
            f"<td>{desc}</td>"
            f"</tr>\n"
        )
        type_detail = _type_detail_html(p.annotation or "", stypes)
        if type_detail:
            input_rows += (
                f'      <tr><td colspan="{ncols}" class="speks-contract-nested">{type_detail}</td></tr>\n'
            )

    if not input_rows:
        input_rows = f'      <tr><td colspan="{ncols}"><em>{t("contract.no_params")}</em></td></tr>\n'

    ret = html_mod.escape(info.return_annotation or "—")  # type: ignore[attr-defined]
    ret_desc = html_mod.escape(info.return_description) if info.return_description else "—"  # type: ignore[attr-defined]
    ret_type_detail = _type_detail_html(info.return_annotation or "", stypes)  # type: ignore[attr-defined]
    ret_detail_row = ""
    if ret_type_detail:
        ret_detail_row = (
            f'      <tr><td colspan="{ncols}" class="speks-contract-nested">{ret_type_detail}</td></tr>\n'
        )

    doc_html = ""
    if info.docstring:  # type: ignore[attr-defined]
        doc_html = f'  <p class="speks-contract-doc">{html_mod.escape(info.docstring)}</p>\n'  # type: ignore[attr-defined]

    return f"""\
<div class="speks-contract" markdown="0">
  <h4 class="speks-contract-title"><code>{html_mod.escape(func_name)}</code></h4>
{doc_html}  <table class="speks-contract-table">
    <thead>
      <tr><th colspan="{ncols}" class="speks-contract-section">{t("contract.inputs")}</th></tr>
      <tr><th>{t("contract.parameter")}</th><th>{t("contract.type")}</th><th>{t("contract.default")}</th><th>{t("contract.description")}</th></tr>
    </thead>
    <tbody>
{input_rows}    </tbody>
    <thead>
      <tr><th colspan="{ncols}" class="speks-contract-section">{t("contract.output")}</th></tr>
    </thead>
    <tbody>
      <tr><td><code>return</code></td><td><code>{ret}</code></td><td>—</td><td>{ret_desc}</td></tr>
{ret_detail_row}    </tbody>
  </table>
</div>
"""


# ---------------------------------------------------------------------------
# playground
# ---------------------------------------------------------------------------


def _resolve_type_name(type_str: str, structured_types: dict[str, StructuredTypeInfo]) -> StructuredTypeInfo | None:
    """Find a StructuredTypeInfo for a type string, stripping wrappers."""
    if not type_str or not structured_types:
        return None
    for candidate in (type_str, _strip_generic_wrapper(type_str) or ""):
        short = candidate.rsplit(".", 1)[-1]
        if short in structured_types:
            return structured_types[short]
    return None


def _build_structured_fields(
    param_name: str,
    type_info: StructuredTypeInfo,
    structured_types: dict[str, StructuredTypeInfo],
    qualified_name: str,
    path_prefix: str,
    *,
    seen: set[str] | None = None,
    indent: int = 2,
) -> str:
    """Recursively build HTML input fields for a structured Pydantic/dataclass type."""
    if seen is None:
        seen = set()
    if type_info.name in seen:
        return ""
    seen = seen | {type_info.name}

    pad = "  " * indent
    comment_html = ""
    if type_info.docstring:
        comment_html = f' <em class="speks-contract-field-comment">{html_mod.escape(type_info.docstring)}</em>'
    html = (
        f'{pad}<fieldset class="speks-structured-group" data-param="{html_mod.escape(path_prefix)}">\n'
        f'{pad}  <legend>{html_mod.escape(param_name)} '
        f'<code>({html_mod.escape(type_info.name)})</code>{comment_html}</legend>\n'
    )

    for f in type_info.fields:
        f_path = f"{path_prefix}.{f.name}"
        f_id = f"speks-{qualified_name}-{f_path}"
        f_ann = f.annotation or "str"
        f_comment = ""
        if f.comment:
            f_comment = f' <em class="speks-contract-field-comment">{html_mod.escape(f.comment)}</em>'

        # Check if this field is itself a structured type
        nested_type = _resolve_type_name(f_ann, structured_types)
        if nested_type and nested_type.name not in seen:
            html += _build_structured_fields(
                f.name, nested_type, structured_types, qualified_name,
                f_path, seen=seen, indent=indent + 1,
            )
        else:
            # Determine the base type for the input (strip Optional/Union wrappers)
            bare = _strip_generic_wrapper(f_ann) or f_ann
            input_type = "number" if bare in ("int", "float") else "text"
            if bare == "bool":
                input_type = "text"  # use text; user enters true/false
            step = 'step="any"' if bare == "float" else ""
            default_val = html_mod.escape(f.default) if f.default else ""
            req_attr = "required" if f.required else ""
            req_mark = ' <span class="speks-required">*</span>' if f.required else ""
            html += (
                f'{pad}  <div class="speks-field">'
                f'<label for="{f_id}">'
                f'{f.name} <code>({html_mod.escape(f_ann)})</code>{req_mark}{f_comment}</label>'
                f'<input id="{f_id}" '
                f'class="speks-structured-input" '
                f'data-path="{html_mod.escape(f_path)}" '
                f'type="{input_type}" {step} '
                f'value="{default_val}" placeholder="{f.name}" {req_attr}>'
                f"</div>\n"
            )

    html += f"{pad}</fieldset>\n"
    return html


def resolve_playground(arg: str, root: Path, *, mode: Mode = "mkdocs") -> str:
    """``@[playground](file.py:func)`` or ``@[playground](file.py:Class:method)``."""
    file_part, class_name, func_name = parse_tag_arg(arg)
    if not func_name:
        return "<!-- speks: playground tag requires file:function format -->"

    file_path = root / file_part
    if not file_path.exists():
        return f"<!-- speks: file not found: {file_part} -->"

    try:
        info = extract_function(file_path, func_name, class_name=class_name)
    except ValueError:
        label = f"{class_name}:{func_name}" if class_name else func_name
        return f"<!-- speks: function '{label}' not found in {file_part} -->"

    # Qualified name for HTML ids and API calls
    qualified_name = f"{class_name}.{func_name}" if class_name else func_name

    if mode == "markdown":
        return (
            f'<div class="speks-playground" '
            f'data-function="{qualified_name}" '
            f'data-source="{file_part}"></div>'
        )

    # ----- HTML widget (mkdocs / standalone) -----

    structured_types = _collect_structured_types(file_path, root)

    fields = ""
    for p in info.parameters:
        ann = p.annotation or "str"
        # Check if this parameter is a structured (Pydantic/dataclass) type
        type_info = _resolve_type_name(ann, structured_types)
        if type_info:
            fields += _build_structured_fields(
                p.name, type_info, structured_types, qualified_name, p.name,
            )
        else:
            default = p.default or ""
            input_type = "number" if ann in ("int", "float") else "text"
            step = 'step="any"' if ann == "float" else ""
            required_attr = "required" if p.default is None else ""
            required_mark = ' <span class="speks-required">*</span>' if p.default is None else ""
            fields += (
                f'  <div class="speks-field">'
                f'<label for="speks-{qualified_name}-{p.name}">'
                f'{p.name} <code>({ann})</code>{required_mark}</label>'
                f'<input id="speks-{qualified_name}-{p.name}" '
                f'name="{p.name}" type="{input_type}" {step} '
                f'value="{default}" placeholder="{p.name}" {required_attr}>'
                f"</div>\n"
            )

    mock_fields = _build_mock_fields(file_path, root, qualified_name)

    docstring_html = (
        f'  <p class="speks-doc">{info.docstring}</p>\n' if info.docstring else ""
    )

    if mode == "standalone":
        button = (
            '    <button type="button" class="speks-run-btn" disabled '
            f'title="{t("playground.disabled_tooltip")}">\n'
            f"      {t('playground.run_button')}\n"
            "    </button>\n"
        )
        result_div = ""
        save_btn = ""
    else:
        button = (
            f'    <button type="button" class="speks-run-btn" onclick="swRunFunction(this)">\n'
            f"      {t('playground.run_button')}\n"
            f"    </button>\n"
        )
        result_div = f'  <div class="speks-result" id="speks-result-{qualified_name}"></div>\n'
        save_btn = (
            f'  <div class="speks-tc-actions">\n'
            f'    <button type="button" class="speks-tc-save-btn" disabled '
            f'onclick="swSaveTestCase(this)" data-function="{qualified_name}">'
            f'{t("tc.save")}</button>\n'
            f"  </div>\n"
        )

    tc_panel = _build_testcase_panel(root, qualified_name, mode)

    return (
        f'\n<details class="speks-playground-widget" data-function="{qualified_name}" markdown="0">\n'
        f"  <summary><h4>{t('playground.title')} — <code>{qualified_name}</code></h4></summary>\n"
        f"{docstring_html}"
        f'  <details class="speks-source-details">\n'
        f"    <summary>{t('playground.view_source')}</summary>\n"
        f'    <pre><code class="language-python">{info.source}</code></pre>\n'
        f"  </details>\n"
        f'  <form class="speks-playground-form" data-function="{qualified_name}" onsubmit="return false;">\n'
        f"{fields}{mock_fields}"
        f"{button}"
        f"  </form>\n"
        f"{result_div}"
        f"{save_btn}"
        f"{tc_panel}"
        f"</details>\n"
    )


def _build_mock_fields(file_path: Path, root: Path, func_name: str) -> str:
    """Build mock configuration fields via static dependency analysis."""
    import json as json_mod

    from speks.core.dependency_analyzer import analyze_directory, get_service_mock_defaults

    try:
        src_dir = file_path.parent
        graph = analyze_directory(src_dir, root)
        mock_defaults = get_service_mock_defaults(graph, func_name)
    except Exception:
        return ""

    if not mock_defaults:
        return ""

    mock_fields = '  <details class="speks-mock-config" open>\n'
    mock_fields += f'    <summary>{t("playground.mock_config")}</summary>\n'
    for svc in mock_defaults:
        svc_name = svc["name"]
        svc_display = svc.get("display_name") or svc_name
        svc_doc = svc["docstring"] or ""
        doc_html = f" <em>— {html_mod.escape(svc_doc)}</em>" if svc_doc else ""
        mock_fields += (
            f'    <div class="speks-mock-field">\n'
            f'      <label for="speks-mock-{func_name}-{svc_name}">'
            f'{html_mod.escape(svc_display)}{doc_html}</label>\n'
        )

        pydantic_fields = svc.get("pydantic_fields")
        if pydantic_fields:
            # Render individual input fields for each Pydantic model field
            mock_fields += (
                f'      <div class="speks-mock-pydantic" data-service="{svc_name}">\n'
            )
            for pf in pydantic_fields:
                pf_name = pf["name"]
                pf_ann = pf["annotation"]
                pf_default = pf.get("default")
                pf_default_str = "" if pf_default is None else html_mod.escape(str(pf_default))
                input_type = "number" if pf_ann in ("int", "float") else "text"
                step = 'step="any"' if pf_ann == "float" else ""
                mock_fields += (
                    f'        <div class="speks-mock-pydantic-field">'
                    f'<label for="speks-mock-{func_name}-{svc_name}-{pf_name}">'
                    f'{pf_name} <code>({pf_ann})</code></label>'
                    f'<input id="speks-mock-{func_name}-{svc_name}-{pf_name}" '
                    f'class="speks-mock-pydantic-input" '
                    f'data-service="{svc_name}" data-field="{pf_name}" '
                    f'type="{input_type}" {step} '
                    f'value="{pf_default_str}" placeholder="{pf_name}">'
                    f"</div>\n"
                )
            mock_fields += "      </div>\n"
        else:
            # Fallback: raw JSON textarea
            default_json = html_mod.escape(svc["default_json"])
            mock_fields += (
                f'      <textarea id="speks-mock-{func_name}-{svc_name}" '
                f'class="speks-mock-input" '
                f'data-service="{svc_name}">{default_json}</textarea>\n'
            )

        # Error mock section — structured fields for MockErrorResponse
        error_default = svc.get("error_default") or {
            "error_code": "ERR_EXAMPLE",
            "error_message": "Example error",
            "http_code": 500,
        }
        err_code = html_mod.escape(str(error_default.get("error_code", "ERR_EXAMPLE")))
        err_msg = html_mod.escape(str(error_default.get("error_message", "Example error")))
        err_http = error_default.get("http_code", 500)
        mock_fields += (
            f'      <div class="speks-error-mock">\n'
            f'        <label class="speks-error-toggle">\n'
            f'          <input type="checkbox" class="speks-error-checkbox" '
            f'data-service="{svc_name}">\n'
            f'          {t("playground.simulate_error")}\n'
            f'        </label>\n'
            f'        <div class="speks-error-fields" data-service="{svc_name}">\n'
            f'          <div class="speks-error-field">'
            f'<label for="speks-errcode-{func_name}-{svc_name}">'
            f'error_code</label>'
            f'<input id="speks-errcode-{func_name}-{svc_name}" '
            f'class="speks-error-field-input" data-service="{svc_name}" '
            f'data-error-field="error_code" type="text" '
            f'value="{err_code}" disabled></div>\n'
            f'          <div class="speks-error-field">'
            f'<label for="speks-errmsg-{func_name}-{svc_name}">'
            f'error_message</label>'
            f'<input id="speks-errmsg-{func_name}-{svc_name}" '
            f'class="speks-error-field-input" data-service="{svc_name}" '
            f'data-error-field="error_message" type="text" '
            f'value="{err_msg}" disabled></div>\n'
            f'          <div class="speks-error-field">'
            f'<label for="speks-errhttp-{func_name}-{svc_name}">'
            f'http_code</label>'
            f'<input id="speks-errhttp-{func_name}-{svc_name}" '
            f'class="speks-error-field-input" data-service="{svc_name}" '
            f'data-error-field="http_code" type="number" '
            f'value="{err_http}" disabled></div>\n'
            f'        </div>\n'
            f'      </div>\n'
            f"    </div>\n"
        )
    mock_fields += "  </details>\n"
    return mock_fields


def _build_testcase_panel(root: Path, func_name: str, mode: Mode) -> str:
    """Build the test-case panel HTML for a playground widget."""
    import json as json_mod

    try:
        cases = load_testcases(root, func_name)
    except Exception:
        cases = []

    interactive = mode == "mkdocs"

    items = ""
    for tc in cases:
        tc_id = html_mod.escape(tc.id, quote=True)
        tc_json = html_mod.escape(json_mod.dumps(
            {"inputs": tc.inputs, "mocks": tc.mocks, "expected": tc.expected,
             "error_mocks": tc.error_mocks},
            ensure_ascii=False,
        ))
        badge = f'<span class="speks-tc-badge" id="speks-tc-badge-{tc_id}"></span>'
        if interactive:
            replay_btn = (
                f'<button type="button" class="speks-tc-btn" '
                f'onclick="swReplayTestCase(this, \'{tc_id}\')" '
                f'data-function="{func_name}" data-tc=\'{tc_json}\'>'
                f'{t("tc.replay")}</button>'
            )
            delete_btn = (
                f'<button type="button" class="speks-tc-btn danger" '
                f'onclick="swDeleteTestCase(this, \'{tc_id}\')" '
                f'data-function="{func_name}">'
                f'{t("tc.delete")}</button>'
            )
        else:
            replay_btn = (
                f'<button type="button" class="speks-tc-btn" disabled>'
                f'{t("tc.replay")}</button>'
            )
            delete_btn = ""
        items += (
            f'    <li class="speks-tc-item" id="speks-tc-{tc_id}">'
            f'<span class="speks-tc-name">{html_mod.escape(tc.name)}</span>'
            f'{badge}{replay_btn}{delete_btn}'
            f'</li>\n'
        )

    if not items:
        items = f'    <li class="speks-tc-item"><em>{t("tc.no_testcases")}</em></li>\n'

    replay_all = ""
    if cases and interactive:
        replay_all = (
            f'    <button type="button" class="speks-tc-btn" '
            f'onclick="swReplayAll(this)" data-function="{func_name}" '
            f'style="margin-top:.4rem">{t("tc.replay_all")}</button>\n'
            f'    <span class="speks-tc-summary" id="speks-tc-summary-{func_name}"></span>\n'
        )

    return (
        f'  <details class="speks-testcases" open>\n'
        f'    <summary>{t("tc.panel_title")}</summary>\n'
        f'    <ul class="speks-tc-list" id="speks-tc-list-{func_name}">\n'
        f'{items}'
        f'    </ul>\n'
        f'{replay_all}'
        f'  </details>\n'
    )
