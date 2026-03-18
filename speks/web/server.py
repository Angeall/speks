"""Local development server with FastAPI.

Serves the generated static site and exposes ``POST /api/run`` so the
interactive playground can execute business-rule functions with mocking
enabled.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import sys
import types
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from speks.core.config import ProjectConfig, load_config
from speks.i18n import t

# ---------------------------------------------------------------------------
# JSON-safe conversion (handles Pydantic models, dataclasses, etc.)
# ---------------------------------------------------------------------------


def _make_json_safe(obj: Any) -> Any:
    """Recursively convert an object to JSON-serializable primitives."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):  # Pydantic BaseModel
        return obj.model_dump()
    if hasattr(obj, "__dataclass_fields__"):  # dataclass
        import dataclasses
        return {k: _make_json_safe(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    return str(obj)


from speks.engine.mocking import (
    ServiceError,
    clear_call_log,
    clear_error_overrides,
    clear_mock_overrides,
    get_call_log,
    set_error_overrides,
    set_mock_mode,
    set_mock_overrides,
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    function: str
    args: dict[str, object]
    mock_overrides: dict[str, object] = {}
    error_overrides: dict[str, dict[str, Any]] = {}


class SaveTestCaseRequest(BaseModel):
    name: str
    inputs: dict[str, object]
    mocks: dict[str, object] = {}
    expected: object = None
    error_mocks: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(project_root: Path, site_dir: Path) -> FastAPI:
    """Return a FastAPI app that serves the site and the run API."""
    app = FastAPI(title=t("server.title"))

    config = load_config(project_root)
    _run_timeout: int = config.run_timeout

    # Thread pool for running user functions concurrently without blocking
    # the async event loop.
    _executor = ThreadPoolExecutor(max_workers=4)

    # Pre-load user source modules
    src_dir = project_root / "src"
    _user_modules = _load_user_modules(src_dir) if src_dir.is_dir() else {}

    def _execute_user_function(
        func: Callable[..., Any], coerced: dict[str, object],
        mock_overrides: dict[str, object] | None,
        error_overrides: dict[str, dict[str, Any]] | None,
    ) -> tuple[Any, list[Any], dict[str, Any] | None]:
        """Run a user function with mocking set up (called in worker thread)."""
        set_mock_mode(True)
        clear_call_log()
        if mock_overrides:
            set_mock_overrides(dict(mock_overrides))
        else:
            clear_mock_overrides()
        if error_overrides:
            set_error_overrides(dict(error_overrides))
        else:
            clear_error_overrides()
        try:
            result = func(**coerced)
            return result, get_call_log(), None
        except ServiceError as exc:
            error_info = {
                "service": exc.service_name,
                "error_code": exc.error_code,
                "error_message": exc.error_message,
                "http_code": exc.http_code,
            }
            return None, get_call_log(), error_info

    @app.post("/api/run")
    async def run_function(req: RunRequest) -> JSONResponse:
        func = _find_function(req.function, _user_modules)
        if func is None:
            return JSONResponse(
                {"success": False, "error": t("server.func_not_found", name=req.function)},
                status_code=404,
            )

        # Coerce arguments to match annotations (safe types only)
        _SAFE_COERCE_TYPES = (int, float, str, bool, list, dict, tuple)
        sig = inspect.signature(func)
        coerced: dict[str, object] = {}
        for name, param in sig.parameters.items():
            if name not in req.args:
                continue
            value = req.args[name]
            ann = param.annotation
            if ann is not inspect.Parameter.empty and ann in _SAFE_COERCE_TYPES:
                try:
                    value = ann(value)
                except (TypeError, ValueError):
                    pass
            coerced[name] = value

        try:
            future = _executor.submit(
                _execute_user_function, func, coerced,
                dict(req.mock_overrides) if req.mock_overrides else None,
                dict(req.error_overrides) if req.error_overrides else None,
            )
            result, call_log, service_error = future.result(timeout=_run_timeout)
            if service_error is not None:
                return JSONResponse({
                    "success": False,
                    "service_error": service_error,
                    "call_log": _make_json_safe(call_log),
                    "error": f"[{service_error['service']}] "
                             f"{service_error['error_code']}: {service_error['error_message']}"
                             + (f" (HTTP {service_error['http_code']})" if service_error.get('http_code') else ""),
                })
            return JSONResponse({"success": True, "result": _make_json_safe(result), "call_log": _make_json_safe(call_log)})
        except TimeoutError:
            return JSONResponse(
                {"success": False, "error": t("server.timeout", seconds=_run_timeout)},
                status_code=504,
            )
        except Exception as exc:
            return JSONResponse({"success": False, "error": str(exc)}, status_code=500)

    # ----- Test case endpoints -------------------------------------------------

    from speks.core.testcases import (
        TestCase,
        _validate_func_name,
        delete_testcase,
        load_testcases,
        save_testcase,
    )

    @app.get("/api/testcases/{function}")
    async def list_testcases(function: str) -> JSONResponse:
        try:
            _validate_func_name(function)
        except ValueError:
            return JSONResponse({"error": "invalid function name"}, status_code=400)
        cases = load_testcases(project_root, function)
        return JSONResponse([
            {"id": tc.id, "name": tc.name, "inputs": tc.inputs,
             "mocks": tc.mocks, "expected": tc.expected,
             "error_mocks": tc.error_mocks}
            for tc in cases
        ])

    @app.post("/api/testcases/{function}")
    async def create_testcase(function: str, req: SaveTestCaseRequest) -> JSONResponse:
        try:
            _validate_func_name(function)
        except ValueError:
            return JSONResponse({"error": "invalid function name"}, status_code=400)
        tc = TestCase(id="", name=req.name, inputs=dict(req.inputs),
                      mocks=dict(req.mocks), expected=req.expected,
                      error_mocks=dict(req.error_mocks))
        saved = save_testcase(project_root, function, tc)
        return JSONResponse(
            {"id": saved.id, "name": saved.name, "inputs": saved.inputs,
             "mocks": saved.mocks, "expected": saved.expected,
             "error_mocks": saved.error_mocks},
            status_code=201,
        )

    @app.delete("/api/testcases/{function}/{testcase_id}")
    async def remove_testcase(function: str, testcase_id: str) -> JSONResponse:
        try:
            _validate_func_name(function)
        except ValueError:
            return JSONResponse({"error": "invalid function name"}, status_code=400)
        found = delete_testcase(project_root, function, testcase_id)
        if not found:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deleted": testcase_id})

    # ----- Versioning / diff endpoints ----------------------------------------

    @app.get("/api/versions")
    async def list_versions() -> JSONResponse:
        versions_path = site_dir / "versions.json"
        if not versions_path.is_file():
            return JSONResponse([])
        import json as _json
        return JSONResponse(_json.loads(versions_path.read_text(encoding="utf-8")))

    @app.get("/api/diff")
    async def get_diff(
        page: str,
        from_rev: str,
        to_rev: str,
    ) -> JSONResponse:
        """Return a unified diff of a documentation page between two revisions.

        ``from_rev`` and ``to_rev`` can be git SHAs or ``"current"``.
        ``page`` is the relative path within the docs directory (e.g. ``index.html``).
        """
        import difflib

        from speks.core.git import get_file_at_revision, is_git_repo

        if not is_git_repo(project_root):
            return JSONResponse(
                {"error": "Not a git repository"}, status_code=400,
            )

        # Map the HTML page path back to the markdown source
        md_page = _html_path_to_md(page, config)

        from_content = _get_page_content(
            project_root, config, from_rev, md_page, get_file_at_revision,
        )
        to_content = _get_page_content(
            project_root, config, to_rev, md_page, get_file_at_revision,
        )

        from_lines = from_content.splitlines(keepends=True) if from_content else []
        to_lines = to_content.splitlines(keepends=True) if to_content else []

        from_label = from_rev if from_rev != "current" else "current"
        to_label = to_rev if to_rev != "current" else "current"

        diff = difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"{md_page} ({from_label})",
            tofile=f"{md_page} ({to_label})",
            lineterm="",
        )
        unified = "\n".join(diff)

        return JSONResponse({
            "has_changes": bool(unified),
            "unified_diff": unified,
            "from_rev": from_rev,
            "to_rev": to_rev,
            "page": md_page,
        })

    # Serve static site (must be mounted AFTER API routes)
    if site_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(site_dir), html=True), name="static")

    return app


def _html_path_to_md(page_path: str, config: ProjectConfig) -> str:
    """Convert an HTML page path to its corresponding Markdown source path.

    Examples:
        ``index.html``        → ``docs/index.md``
        ``intro/index.html``  → ``docs/intro.md`` or ``docs/intro/index.md``
        ``intro/``            → ``docs/intro.md`` or ``docs/intro/index.md``
    """
    p = page_path.rstrip("/")
    if not p or p == "index.html":
        return f"{config.docs_dir}/index.md"

    # Remove trailing /index.html
    if p.endswith("/index.html"):
        p = p[: -len("/index.html")]

    # Try <section>.md first, then <section>/index.md
    # Return the path; callers will check existence
    return f"{config.docs_dir}/{p}.md"


def _get_page_content(
    project_root: Path,
    config: ProjectConfig,
    revision: str,
    md_path: str,
    get_file_fn: Callable[..., str | None],
) -> str:
    """Retrieve markdown content for a page at a given revision."""
    if revision == "current":
        full = project_root / md_path
        if full.is_file():
            return full.read_text(encoding="utf-8")
        # Try index.md variant
        alt = project_root / md_path.replace(".md", "/index.md")
        if alt.is_file():
            return alt.read_text(encoding="utf-8")
        return ""

    content: str | None = get_file_fn(project_root, revision, md_path)
    if content is not None:
        return content
    # Try index.md variant
    alt_path = md_path.replace(".md", "/index.md")
    content = get_file_fn(project_root, revision, alt_path)
    return content if content is not None else ""


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------


def _load_user_modules(src_dir: Path) -> dict[str, types.ModuleType]:
    """Import every ``.py`` file under *src_dir* and return a name→module map.

    The *src_dir* is registered as a real package (``_sw_user_``) so that
    relative imports between user modules (e.g. ``from .regles import …``)
    resolve correctly.
    """
    package_name = "_sw_user_"

    # Create a proper package so relative imports work.
    pkg = types.ModuleType(package_name)
    pkg.__path__ = [str(src_dir)]
    pkg.__package__ = package_name
    sys.modules[package_name] = pkg

    modules: dict[str, types.ModuleType] = {}

    for py_file in sorted(src_dir.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        module_name = f"{package_name}.{py_file.stem}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            py_file,
            submodule_search_locations=[],
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = package_name
            sys.modules[module_name] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception:
                continue
            modules[py_file.stem] = mod
    return modules


def _find_function(
    name: str,
    user_modules: dict[str, types.ModuleType],
) -> Callable[..., Any] | None:
    """Search user modules for a callable named *name*.

    Supports dotted names like ``ClassName.method`` for class methods.
    Only returns functions that are **defined** in a user module (i.e. whose
    ``__module__`` starts with the ``_sw_user_`` package prefix).  Imported
    callables (e.g. ``os.system``) are excluded to prevent arbitrary code
    execution.
    """
    # Support Class.method syntax
    if "." in name:
        class_name, method_name = name.split(".", 1)
        for mod in user_modules.values():
            cls = getattr(mod, class_name, None)
            if cls is None or not isinstance(cls, type):
                continue
            obj_module = getattr(cls, "__module__", None) or ""
            if not obj_module.startswith("_sw_user_"):
                continue
            method = getattr(cls, method_name, None)
            if method is not None and callable(method):
                # Return an unbound function that instantiates the class
                klass: type = cls
                def _bound_method(
                    *args: Any, _cls: type = klass, _method: str = method_name, **kwargs: Any,
                ) -> Any:
                    return getattr(_cls(), _method)(*args, **kwargs)
                return cast(Callable[..., Any], _bound_method)
        return None

    for mod in user_modules.values():
        obj = getattr(mod, name, None)
        if obj is None or not callable(obj):
            continue
        # Only allow functions actually defined in user code
        obj_module = getattr(obj, "__module__", None) or ""
        if obj_module.startswith("_sw_user_"):
            return cast(Callable[..., Any], obj)
    return None
