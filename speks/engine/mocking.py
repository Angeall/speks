"""Mocking engine for external service simulation.

Analysts declare external service entities with a ``@service`` class
decorator and mark each outgoing call with a ``@stub`` method decorator.
At runtime, when mock mode is active, the decorated method returns the
static ``mock=`` value from the decorator (or an override pushed via
``set_mock_overrides``) instead of calling the real implementation.

Example::

    from speks import service, stub, MockError, ServiceError

    @service
    class CoreBanking:
        '''Core Banking API (blackbox).'''

        @stub(
            mock=ClientBalance(balance=1500.0, currency="USD"),
            error=MockError("CLIENT_NOT_FOUND", "Not found", http_code=404),
        )
        def check_balance(self, client_id: str) -> ClientBalance:
            '''Fetch the client's current balance.'''
            ...  # real implementation (HTTP/SQL)
"""

from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, TypeVar

# ---------------------------------------------------------------------------
# Context-aware execution mode
# ---------------------------------------------------------------------------

_mock_mode: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_mock_mode", default=True
)

_mock_overrides: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "_mock_overrides", default={}
)

_error_overrides: contextvars.ContextVar[dict[str, dict[str, Any]]] = contextvars.ContextVar(
    "_error_overrides", default={}
)


def set_mock_mode(enabled: bool) -> None:
    """Enable or disable mock mode for the current context."""
    _mock_mode.set(enabled)


def is_mock_mode() -> bool:
    """Return whether mock mode is active."""
    return _mock_mode.get()


def set_mock_overrides(overrides: dict[str, Any]) -> None:
    """Set per-stub mock-data overrides for the current context.

    Keys are dotted names of the form ``"ClassName.method_name"``
    (e.g. ``"CoreBanking.check_balance"``).  The associated value
    replaces the ``mock=`` default from the decorator.
    """
    _mock_overrides.set(overrides)


def clear_mock_overrides() -> None:
    """Remove all mock overrides for the current context."""
    _mock_overrides.set({})


def set_error_overrides(overrides: dict[str, dict[str, Any]]) -> None:
    """Set per-stub error overrides for the current context.

    Keys follow the same dotted convention as ``set_mock_overrides``.
    Each value is a dict with ``error_code``, ``error_message`` and an
    optional ``http_code``.  When an error override is active for a
    stub, calling the stub raises :class:`ServiceError` instead of
    returning data.
    """
    _error_overrides.set(overrides)


def clear_error_overrides() -> None:
    """Remove all error overrides for the current context."""
    _error_overrides.set({})


# ---------------------------------------------------------------------------
# MockError & ServiceError
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MockError:
    """Describes an error that a stub can raise in mock mode.

    Parameters
    ----------
    error_code:
        Application-level error code (e.g. ``"INSUFFICIENT_FUNDS"``).
    error_message:
        Human-readable error description.
    http_code:
        Optional HTTP status code (e.g. ``503``).  May be ``None`` when
        the error is not HTTP-related.
    """

    error_code: str
    error_message: str
    http_code: int | None = None


class ServiceError(Exception):
    """Raised when a stub is called with an active error override.

    Carries the structured error information so that business rules can
    inspect ``service_name``, ``method_name``, ``error_code``,
    ``error_message`` and ``http_code``.
    """

    def __init__(self, service_name: str, method_name: str, error: MockError) -> None:
        self.service_name = service_name
        self.method_name = method_name
        self.error_code = error.error_code
        self.error_message = error.error_message
        self.http_code = error.http_code
        full_name = f"{service_name}.{method_name}"
        parts = [f"[{full_name}] {error.error_code}: {error.error_message}"]
        if error.http_code is not None:
            parts.append(f"(HTTP {error.http_code})")
        super().__init__(" ".join(parts))


# ---------------------------------------------------------------------------
# Call log (for introspection / assertions in the playground)
# ---------------------------------------------------------------------------

_call_log_lock = threading.Lock()
_call_log: list[dict[str, Any]] = []


def get_call_log() -> list[dict[str, Any]]:
    """Return a copy of the call log."""
    with _call_log_lock:
        return list(_call_log)


def clear_call_log() -> None:
    """Reset the call log."""
    with _call_log_lock:
        _call_log.clear()


def _record_call(
    full_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
    mocked: bool,
    *,
    error: dict[str, Any] | None = None,
) -> None:
    with _call_log_lock:
        entry: dict[str, Any] = {
            "service": full_name,
            "args": args,
            "kwargs": kwargs,
            "result": result,
            "mocked": mocked,
        }
        if error is not None:
            entry["error"] = error
        _call_log.append(entry)


# ---------------------------------------------------------------------------
# Pydantic override coercion
# ---------------------------------------------------------------------------


def _maybe_coerce_to_pydantic(default_mock: Any, override: Any) -> Any:
    """Reconstruct a Pydantic model from *override* when *default_mock* is one.

    The playground sends field overrides as plain JSON dicts.  If the
    stub's static ``mock=`` value is a Pydantic ``BaseModel`` instance,
    we rebuild an instance of the same class so that business code can
    keep accessing fields via attribute syntax.

    Coercion strategy (each step tried in order, first success wins):

    1. Validate the override dict as-is.
    2. JSON-parse / ``ast.literal_eval`` string values that look like
       complex literals (``"[1,2]"``, ``"{...}"``), then re-validate.
    3. Per-field merge: start from the default mock, and for each
       override field try ``model_validate`` with that single change;
       keep the override if it validates, fall back to the default
       value otherwise.  Guarantees a valid model instance is returned
       even when the user typed garbage in one field.
    4. Last resort: return the default mock unchanged.

    The function NEVER returns a raw dict — that would crash business
    code that accesses fields via attribute syntax.
    """
    if not isinstance(override, dict):
        return override
    if default_mock is None:
        return override
    model_cls = type(default_mock)
    if not (hasattr(model_cls, "model_validate") and hasattr(model_cls, "model_fields")):
        return override

    # 1. Validate as-is.
    try:
        return model_cls.model_validate(override)
    except Exception:
        pass

    # 2. JSON / Python-literal parse for stringified complex values.
    import ast as _ast
    import json as _json

    patched = dict(override)
    for key, value in patched.items():
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if not stripped or stripped[:1] not in ("[", "{", "("):
            continue
        for parser in (_json.loads, _ast.literal_eval):
            try:
                patched[key] = parser(stripped)
                break
            except Exception:
                continue
    try:
        return model_cls.model_validate(patched)
    except Exception:
        pass

    # 3. Per-field merge with default fallback.  Starts from the
    #    serialised default mock, then tries to swap in each override
    #    one at a time.  Invalid fields stay at their default.
    try:
        merged = default_mock.model_dump()
        fields = set(getattr(model_cls, "model_fields", {}).keys())
        for key, value in patched.items():
            if key not in fields:
                continue
            candidate = {**merged, key: value}
            try:
                validated = model_cls.model_validate(candidate)
            except Exception:
                continue
            # Use the validated value (Pydantic may have coerced it).
            merged[key] = validated.model_dump()[key]
        return model_cls.model_validate(merged)
    except Exception:
        pass

    # 4. Last resort: hand the business code the untouched default.
    return default_mock


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

_SERVICE_META = "_speks_service_meta"
_STUB_META = "_speks_stub_meta"

F = TypeVar("F", bound=Callable[..., Any])


def service(cls: type | None = None, *, description: str | None = None) -> Any:
    """Class decorator marking a class as an external service entity.

    Usage::

        @service
        class CoreBanking:
            '''Core Banking API.'''

        @service(description="Inventory and fulfilment")
        class Warehouse:
            ...

    The decorator attaches a ``_speks_service_meta`` attribute on the
    class and is otherwise a no-op at runtime — ``@stub`` on the methods
    does all the heavy lifting.  Static analysis tools recognise the
    decorator and use the class name as the entity grouping.
    """

    def wrap(klass: type) -> type:
        setattr(
            klass,
            _SERVICE_META,
            {"description": description if description is not None else klass.__doc__},
        )
        return klass

    if cls is None:
        return wrap
    return wrap(cls)


def stub(*, mock: Any = None, error: MockError | None = None) -> Callable[[F], F]:
    """Method decorator marking a service method as a mockable stub.

    Parameters
    ----------
    mock:
        Static value returned in mock mode.  May be any Python object
        (Pydantic model instance, dataclass, dict, scalar, ``None``).
    error:
        Optional default :class:`MockError` surfaced in the playground
        so analysts can simulate failure scenarios with one click.

    The wrapped method keeps its original signature and docstring.  In
    mock mode, the body of the method is never executed — either the
    override, the ``mock=`` default, or a :class:`ServiceError` is
    returned/raised.  Out of mock mode the real body runs normally.
    """

    def decorator(func: F) -> F:
        meta = {"mock": mock, "error": error}

        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            service_name = type(self).__name__
            method_name = func.__name__
            full_name = f"{service_name}.{method_name}"

            if is_mock_mode():
                # Error overrides take precedence over data overrides.
                err_ovr = _error_overrides.get({})
                if full_name in err_ovr:
                    ed = err_ovr[full_name]
                    err = MockError(
                        error_code=ed.get("error_code", "UNKNOWN"),
                        error_message=ed.get("error_message", "Unknown error"),
                        http_code=ed.get("http_code"),
                    )
                    _record_call(
                        full_name, args, kwargs, None, mocked=True,
                        error={
                            "error_code": err.error_code,
                            "error_message": err.error_message,
                            "http_code": err.http_code,
                        },
                    )
                    raise ServiceError(service_name, method_name, err)

                m_ovr = _mock_overrides.get({})
                if full_name in m_ovr:
                    result = _maybe_coerce_to_pydantic(mock, m_ovr[full_name])
                    _record_call(full_name, args, kwargs, result, mocked=True)
                    return result

                _record_call(full_name, args, kwargs, mock, mocked=True)
                return mock

            result = func(self, *args, **kwargs)
            _record_call(full_name, args, kwargs, result, mocked=False)
            return result

        setattr(wrapper, _STUB_META, meta)
        return wrapper  # type: ignore[return-value]

    return decorator
