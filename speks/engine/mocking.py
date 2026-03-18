"""Mocking engine for external service simulation.

Provides base classes that analysts use to define external service calls
(HTTP APIs, databases, etc.) with automatic mock injection when running
in test/web mode.
"""

from __future__ import annotations

import contextvars
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

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
    """Set per-service mock data overrides for the current context.

    *overrides* maps service class names (e.g. ``"VerifierSoldeClient"``)
    to the value that should be returned instead of calling ``mock()``.
    """
    _mock_overrides.set(overrides)


def clear_mock_overrides() -> None:
    """Remove all mock overrides for the current context."""
    _mock_overrides.set({})


def set_error_overrides(overrides: dict[str, dict[str, Any]]) -> None:
    """Set per-service error overrides for the current context.

    *overrides* maps service class names to dicts with keys:
    ``error_code``, ``error_message``, and optionally ``http_code``.
    When a service has an error override, calling it raises
    :class:`ServiceError` instead of returning data.
    """
    _error_overrides.set(overrides)


def clear_error_overrides() -> None:
    """Remove all error overrides for the current context."""
    _error_overrides.set({})


# ---------------------------------------------------------------------------
# MockResponse
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MockResponse:
    """Canned response returned by an ExternalService in mock mode.

    Parameters
    ----------
    data:
        Arbitrary payload (dict, list, scalar …) that the mock returns.
    status_code:
        Simulated HTTP status code (useful for HTTP-style services).
    headers:
        Optional response headers.
    """

    data: Any = None
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        """Return *data* — convenience alias that mirrors ``requests``."""
        return self.data


# ---------------------------------------------------------------------------
# MockErrorResponse & ServiceError
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MockErrorResponse:
    """Describes an error returned by an ExternalService.

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
    """Raised when an ExternalService is called in error-mock mode.

    Carries the structured error information so that callers (business
    rules) can inspect ``error_code``, ``error_message``, and
    ``http_code``.
    """

    def __init__(self, service_name: str, error: MockErrorResponse) -> None:
        self.service_name = service_name
        self.error_code = error.error_code
        self.error_message = error.error_message
        self.http_code = error.http_code
        parts = [f"[{service_name}] {error.error_code}: {error.error_message}"]
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
    service_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
    mocked: bool,
    *,
    error: dict[str, Any] | None = None,
) -> None:
    with _call_log_lock:
        entry: dict[str, Any] = {
            "service": service_name,
            "args": args,
            "kwargs": kwargs,
            "result": result,
            "mocked": mocked,
        }
        if error is not None:
            entry["error"] = error
        _call_log.append(entry)


# ---------------------------------------------------------------------------
# ExternalService
# ---------------------------------------------------------------------------


def _maybe_coerce_to_pydantic(
    service: "ExternalService",
    override: dict[str, Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """If the service's default mock returns a Pydantic model, reconstruct it from *override*.

    Falls back to returning the dict unchanged if the mock doesn't use Pydantic
    or if construction fails.
    """
    try:
        response = service.mock(*args, **kwargs)
        default_data = response.data
        model_cls = type(default_data)
        # Check if it's a Pydantic BaseModel (duck-type check to avoid hard dep)
        if hasattr(model_cls, "model_validate") and hasattr(model_cls, "model_fields"):
            return model_cls.model_validate(override)
    except Exception:
        pass
    return override


class ExternalService(ABC):
    """Base class for declaring an external service dependency.

    Subclasses must implement:

    * ``execute(*args, **kwargs)`` — the *real* call (HTTP, SQL, …).
    * ``mock(*args, **kwargs)``    — returns a :class:`MockResponse`.

    Optionally:

    * ``mock_error(*args, **kwargs)`` — returns a :class:`MockErrorResponse`
      describing the default error scenario for this service.
    * ``component_name`` — a class variable grouping related services under
      a logical component (e.g. ``"CoreBanking"``).  When set, the
      playground displays the service as ``ComponentName / ServiceName``.

    At runtime the analyst calls :meth:`call`; the engine transparently
    delegates to ``execute`` or ``mock`` depending on the active mode.
    """

    component_name: ClassVar[str | None] = None

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Perform the real external call."""

    @abstractmethod
    def mock(self, *args: Any, **kwargs: Any) -> MockResponse:
        """Return a canned :class:`MockResponse`."""

    def mock_error(self, *args: Any, **kwargs: Any) -> MockErrorResponse | None:
        """Return a canned :class:`MockErrorResponse`, or ``None``.

        Override this to document the error scenario for this service.
        By default no error mock is provided.
        """
        return None

    def call(self, *args: Any, **kwargs: Any) -> Any:
        """Dispatch to ``mock`` or ``execute`` based on the current mode.

        When mock mode is active, user-supplied overrides (set via
        :func:`set_mock_overrides`) take precedence over the class's
        ``mock()`` method.

        If an error override is active for this service, a
        :class:`ServiceError` is raised instead of returning data.
        """
        class_name = type(self).__name__

        if is_mock_mode():
            # Check error overrides first
            error_ovr = _error_overrides.get({})
            if class_name in error_ovr:
                err_data = error_ovr[class_name]
                err = MockErrorResponse(
                    error_code=err_data.get("error_code", "UNKNOWN"),
                    error_message=err_data.get("error_message", "Unknown error"),
                    http_code=err_data.get("http_code"),
                )
                _record_call(class_name, args, kwargs, None, mocked=True, error={
                    "error_code": err.error_code,
                    "error_message": err.error_message,
                    "http_code": err.http_code,
                })
                raise ServiceError(class_name, err)

            # Normal mock overrides
            overrides = _mock_overrides.get({})
            if class_name in overrides:
                result = overrides[class_name]
                # If the override is a dict, try to reconstruct the Pydantic
                # model that the default mock would return so that user code
                # can access fields via attribute syntax (result.field_name).
                if isinstance(result, dict):
                    result = _maybe_coerce_to_pydantic(self, result, args, kwargs)
                _record_call(class_name, args, kwargs, result, mocked=True)
                return result
            response = self.mock(*args, **kwargs)
            result = response.data
            _record_call(class_name, args, kwargs, result, mocked=True)
            return result
        else:
            result = self.execute(*args, **kwargs)
            _record_call(class_name, args, kwargs, result, mocked=False)
            return result
