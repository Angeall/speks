"""Tests for the mocking engine — ``@service`` / ``@stub`` decorators."""

import pytest

from speks import MockError, ServiceError, service, stub
from speks.engine.mocking import (
    clear_call_log,
    clear_error_overrides,
    clear_mock_overrides,
    get_call_log,
    is_mock_mode,
    set_error_overrides,
    set_mock_mode,
    set_mock_overrides,
)


@service
class FakeAPI:
    """Minimal external service for testing."""

    @stub(mock=42.0)
    def fetch_score(self, user_id: str) -> float:
        # Real implementation that should never run in mock mode.
        return 9999.0


@service
class FakeAPIWithError:
    """Service with a default error stub."""

    @stub(
        mock=42.0,
        error=MockError("NOT_FOUND", "User not found", http_code=404),
    )
    def fetch_score(self, user_id: str) -> float:
        return 9999.0


# ---------------------------------------------------------------------------
# @stub default behaviour
# ---------------------------------------------------------------------------


class TestStubMockMode:
    def setup_method(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_mock_overrides()
        clear_error_overrides()

    def test_returns_mock_value(self) -> None:
        assert FakeAPI().fetch_score("u1") == 42.0

    def test_real_call_when_mock_disabled(self) -> None:
        set_mock_mode(False)
        try:
            assert FakeAPI().fetch_score("u1") == 9999.0
        finally:
            set_mock_mode(True)

    def test_call_log_recorded(self) -> None:
        FakeAPI().fetch_score("u1")
        log = get_call_log()
        assert len(log) == 1
        assert log[0]["service"] == "FakeAPI.fetch_score"
        assert log[0]["mocked"] is True
        assert log[0]["result"] == 42.0

    def test_clear_log(self) -> None:
        FakeAPI().fetch_score("u1")
        clear_call_log()
        assert get_call_log() == []


class TestMockModeContext:
    def test_default_is_mock(self) -> None:
        assert is_mock_mode() is True

    def test_toggle(self) -> None:
        set_mock_mode(False)
        try:
            assert is_mock_mode() is False
        finally:
            set_mock_mode(True)
        assert is_mock_mode() is True


# ---------------------------------------------------------------------------
# Mock overrides (set_mock_overrides)
# ---------------------------------------------------------------------------


class TestMockOverrides:
    def setup_method(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_mock_overrides()
        clear_error_overrides()

    def teardown_method(self) -> None:
        clear_mock_overrides()

    def test_override_replaces_default(self) -> None:
        set_mock_overrides({"FakeAPI.fetch_score": 999.0})
        assert FakeAPI().fetch_score("u1") == 999.0

    def test_override_logged_as_mocked(self) -> None:
        set_mock_overrides({"FakeAPI.fetch_score": 999.0})
        FakeAPI().fetch_score("u1")
        log = get_call_log()
        assert len(log) == 1
        assert log[0]["mocked"] is True
        assert log[0]["result"] == 999.0

    def test_no_override_falls_back_to_default(self) -> None:
        set_mock_overrides({"OtherEntity.method": "x"})
        assert FakeAPI().fetch_score("u1") == 42.0

    def test_dict_override_for_non_pydantic_kept_as_dict(self) -> None:
        set_mock_overrides({"FakeAPI.fetch_score": {"score": 300}})
        assert FakeAPI().fetch_score("u1") == {"score": 300}

    def test_clear_overrides(self) -> None:
        set_mock_overrides({"FakeAPI.fetch_score": 0.0})
        clear_mock_overrides()
        assert FakeAPI().fetch_score("u1") == 42.0

    def test_dotted_key_required(self) -> None:
        # Bare class name should NOT match — keys are dotted.
        set_mock_overrides({"FakeAPI": 999.0})
        assert FakeAPI().fetch_score("u1") == 42.0


# ---------------------------------------------------------------------------
# MockError dataclass
# ---------------------------------------------------------------------------


class TestMockError:
    def test_fields(self) -> None:
        err = MockError(error_code="E1", error_message="msg", http_code=500)
        assert err.error_code == "E1"
        assert err.error_message == "msg"
        assert err.http_code == 500

    def test_http_code_optional(self) -> None:
        err = MockError(error_code="E1", error_message="msg")
        assert err.http_code is None

    def test_frozen(self) -> None:
        err = MockError(error_code="E1", error_message="msg")
        with pytest.raises(AttributeError):
            err.error_code = "E2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ServiceError + error overrides
# ---------------------------------------------------------------------------


class TestServiceError:
    def setup_method(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_mock_overrides()
        clear_error_overrides()

    def teardown_method(self) -> None:
        clear_error_overrides()
        clear_mock_overrides()

    def test_raised_from_error_override(self) -> None:
        set_error_overrides({
            "FakeAPI.fetch_score": {
                "error_code": "TIMEOUT",
                "error_message": "Service timed out",
                "http_code": 504,
            }
        })
        with pytest.raises(ServiceError) as exc_info:
            FakeAPI().fetch_score("u1")
        err = exc_info.value
        assert err.service_name == "FakeAPI"
        assert err.method_name == "fetch_score"
        assert err.error_code == "TIMEOUT"
        assert err.error_message == "Service timed out"
        assert err.http_code == 504

    def test_error_recorded_in_call_log(self) -> None:
        set_error_overrides({
            "FakeAPI.fetch_score": {"error_code": "ERR", "error_message": "fail"}
        })
        with pytest.raises(ServiceError):
            FakeAPI().fetch_score("u1")
        log = get_call_log()
        assert len(log) == 1
        assert log[0]["error"]["error_code"] == "ERR"
        assert log[0]["result"] is None
        assert log[0]["mocked"] is True

    def test_error_takes_precedence_over_mock_override(self) -> None:
        set_mock_overrides({"FakeAPI.fetch_score": 999.0})
        set_error_overrides({
            "FakeAPI.fetch_score": {"error_code": "E", "error_message": "m"}
        })
        with pytest.raises(ServiceError):
            FakeAPI().fetch_score("u1")

    def test_no_error_override_returns_normally(self) -> None:
        set_error_overrides({
            "OtherEntity.method": {"error_code": "E", "error_message": "m"}
        })
        assert FakeAPI().fetch_score("u1") == 42.0

    def test_clear_error_overrides(self) -> None:
        set_error_overrides({
            "FakeAPI.fetch_score": {"error_code": "E", "error_message": "m"}
        })
        clear_error_overrides()
        assert FakeAPI().fetch_score("u1") == 42.0

    def test_str_with_http_code(self) -> None:
        err = MockError(error_code="E1", error_message="msg", http_code=503)
        exc = ServiceError("MyService", "do_thing", err)
        s = str(exc)
        assert "[MyService.do_thing] E1: msg" in s
        assert "(HTTP 503)" in s

    def test_str_without_http_code(self) -> None:
        err = MockError(error_code="E1", error_message="msg")
        exc = ServiceError("MyService", "do_thing", err)
        s = str(exc)
        assert "[MyService.do_thing] E1: msg" in s
        assert "HTTP" not in s


# ---------------------------------------------------------------------------
# Pydantic coercion
# ---------------------------------------------------------------------------


class TestPydanticCoercion:
    def setup_method(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_mock_overrides()

    def teardown_method(self) -> None:
        clear_mock_overrides()

    def test_dict_override_coerced_to_pydantic(self) -> None:
        pydantic = pytest.importorskip("pydantic")

        class UserInfo(pydantic.BaseModel):
            name: str
            age: int

        @service
        class UserAPI:
            @stub(mock=UserInfo(name="Alice", age=30))
            def fetch(self, uid: str) -> UserInfo:
                ...

        # Default mock returns the Pydantic instance.
        result = UserAPI().fetch("u1")
        assert isinstance(result, UserInfo)
        assert result.name == "Alice"

        # Dict override is coerced back to a UserInfo.
        clear_call_log()
        set_mock_overrides({"UserAPI.fetch": {"name": "Bob", "age": 25}})
        result = UserAPI().fetch("u1")
        assert isinstance(result, UserInfo)
        assert result.name == "Bob"
        assert result.age == 25

    def test_dict_override_kept_as_dict_for_non_pydantic_default(self) -> None:
        set_mock_overrides({"FakeAPI.fetch_score": {"score": 300}})
        result = FakeAPI().fetch_score("u1")
        assert result == {"score": 300}
        assert isinstance(result, dict)

    def test_scalar_override_not_coerced(self) -> None:
        pydantic = pytest.importorskip("pydantic")

        class Info(pydantic.BaseModel):
            name: str

        @service
        class InfoAPI:
            @stub(mock=Info(name="test"))
            def fetch(self) -> Info:
                ...

        set_mock_overrides({"InfoAPI.fetch": "raw_string"})
        assert InfoAPI().fetch() == "raw_string"

    def test_invalid_list_field_falls_back_to_default(self) -> None:
        """A naive string in a ``list[str]`` field keeps the default."""
        pydantic = pytest.importorskip("pydantic")

        class Record(pydantic.BaseModel):
            name: str
            tags: list[str]

        @service
        class RecordAPI:
            @stub(mock=Record(name="x", tags=["a", "b"]))
            def fetch(self) -> Record:
                ...

        # User types a bare word in `tags` instead of a JSON list.
        set_mock_overrides({
            "RecordAPI.fetch": {"name": "y", "tags": "single-string"},
        })
        result = RecordAPI().fetch()
        assert isinstance(result, Record)
        # Valid override applied:
        assert result.name == "y"
        # Invalid field falls back to default:
        assert result.tags == ["a", "b"]

    def test_partial_override_with_invalid_field_does_not_crash(self) -> None:
        """All-invalid override returns the unchanged default mock."""
        pydantic = pytest.importorskip("pydantic")

        class Account(pydantic.BaseModel):
            balance: float
            owners: list[str]

        @service
        class BankAPI:
            @stub(mock=Account(balance=100.0, owners=["alice"]))
            def fetch(self) -> Account:
                ...

        # Every field invalid.
        set_mock_overrides({
            "BankAPI.fetch": {"balance": "not-a-number", "owners": "alice"},
        })
        result = BankAPI().fetch()
        assert isinstance(result, Account)
        assert result.balance == 100.0
        assert result.owners == ["alice"]


# ---------------------------------------------------------------------------
# Service / stub introspection metadata
# ---------------------------------------------------------------------------


class TestServiceMetadata:
    def test_service_meta_attached_to_class(self) -> None:
        meta = getattr(FakeAPI, "_speks_service_meta", None)
        assert meta is not None
        assert "description" in meta

    def test_service_description_from_docstring(self) -> None:
        meta = FakeAPI._speks_service_meta  # type: ignore[attr-defined]
        assert "Minimal external service" in (meta["description"] or "")

    def test_service_explicit_description(self) -> None:
        @service(description="Banking system")
        class CoreBanking:
            """Original docstring."""

        meta = CoreBanking._speks_service_meta  # type: ignore[attr-defined]
        assert meta["description"] == "Banking system"

    def test_stub_meta_attached_to_method(self) -> None:
        # The @wraps wrapper exposes the metadata via the unbound function.
        meta = getattr(FakeAPIWithError.fetch_score, "_speks_stub_meta", None)
        assert meta is not None
        assert meta["mock"] == 42.0
        assert meta["error"].error_code == "NOT_FOUND"

    def test_stub_preserves_signature_and_docstring(self) -> None:
        import inspect

        sig = inspect.signature(FakeAPI.fetch_score)
        assert "user_id" in sig.parameters
