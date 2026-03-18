"""Tests for the mocking engine (Module A)."""

import pytest

from speks.engine.mocking import (
    ExternalService,
    MockErrorResponse,
    MockResponse,
    ServiceError,
    clear_call_log,
    clear_error_overrides,
    clear_mock_overrides,
    get_call_log,
    is_mock_mode,
    set_error_overrides,
    set_mock_mode,
    set_mock_overrides,
)


class FakeAPI(ExternalService):
    """Minimal external service for testing."""

    def execute(self, user_id: str) -> float:
        return 9999.0

    def mock(self, user_id: str) -> MockResponse:
        return MockResponse(data=42.0)


class FakeAPIWithError(ExternalService):
    """Service with component_name and mock_error."""

    component_name = "MyApp"

    def execute(self, user_id: str) -> float:
        return 9999.0

    def mock(self, user_id: str) -> MockResponse:
        return MockResponse(data=42.0)

    def mock_error(self, user_id: str) -> MockErrorResponse:
        return MockErrorResponse(
            error_code="NOT_FOUND",
            error_message="User not found",
            http_code=404,
        )


class TestMockResponse:
    def test_data_access(self) -> None:
        r = MockResponse(data={"key": "val"})
        assert r.data == {"key": "val"}

    def test_json_alias(self) -> None:
        r = MockResponse(data=[1, 2, 3])
        assert r.json() == [1, 2, 3]

    def test_defaults(self) -> None:
        r = MockResponse()
        assert r.data is None
        assert r.status_code == 200
        assert r.headers == {}


class TestExternalService:
    def setup_method(self) -> None:
        set_mock_mode(True)
        clear_call_log()

    def test_call_in_mock_mode(self) -> None:
        result = FakeAPI().call("u1")
        assert result == 42.0

    def test_call_in_real_mode(self) -> None:
        set_mock_mode(False)
        result = FakeAPI().call("u1")
        assert result == 9999.0
        set_mock_mode(True)  # reset

    def test_call_log_recorded(self) -> None:
        FakeAPI().call("u1")
        log = get_call_log()
        assert len(log) == 1
        assert log[0]["service"] == "FakeAPI"
        assert log[0]["mocked"] is True

    def test_clear_log(self) -> None:
        FakeAPI().call("u1")
        clear_call_log()
        assert get_call_log() == []


class TestMockModeContext:
    def test_default_is_mock(self) -> None:
        assert is_mock_mode() is True

    def test_toggle(self) -> None:
        set_mock_mode(False)
        assert is_mock_mode() is False
        set_mock_mode(True)
        assert is_mock_mode() is True


class TestMockOverrides:
    def setup_method(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_mock_overrides()

    def teardown_method(self) -> None:
        clear_mock_overrides()

    def test_override_replaces_mock_data(self) -> None:
        set_mock_overrides({"FakeAPI": 999.0})
        result = FakeAPI().call("u1")
        assert result == 999.0

    def test_override_logged_as_mocked(self) -> None:
        set_mock_overrides({"FakeAPI": 999.0})
        FakeAPI().call("u1")
        log = get_call_log()
        assert len(log) == 1
        assert log[0]["mocked"] is True
        assert log[0]["result"] == 999.0

    def test_no_override_falls_back_to_mock(self) -> None:
        set_mock_overrides({"SomeOtherService": "x"})
        result = FakeAPI().call("u1")
        assert result == 42.0  # default mock value

    def test_override_with_dict(self) -> None:
        set_mock_overrides({"FakeAPI": {"score": 300, "incidents": 5}})
        result = FakeAPI().call("u1")
        assert result == {"score": 300, "incidents": 5}

    def test_clear_overrides(self) -> None:
        set_mock_overrides({"FakeAPI": 0.0})
        clear_mock_overrides()
        result = FakeAPI().call("u1")
        assert result == 42.0  # back to default mock


class TestComponentName:
    def test_default_is_none(self) -> None:
        assert FakeAPI.component_name is None

    def test_class_var(self) -> None:
        assert FakeAPIWithError.component_name == "MyApp"

    def test_instance_access(self) -> None:
        svc = FakeAPIWithError()
        assert svc.component_name == "MyApp"


class TestMockErrorResponse:
    def test_fields(self) -> None:
        err = MockErrorResponse(error_code="E1", error_message="msg", http_code=500)
        assert err.error_code == "E1"
        assert err.error_message == "msg"
        assert err.http_code == 500

    def test_http_code_optional(self) -> None:
        err = MockErrorResponse(error_code="E1", error_message="msg")
        assert err.http_code is None

    def test_frozen(self) -> None:
        err = MockErrorResponse(error_code="E1", error_message="msg")
        with pytest.raises(AttributeError):
            err.error_code = "E2"  # type: ignore[misc]


class TestServiceError:
    def test_raised_from_error_override(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_error_overrides()
        set_error_overrides({
            "FakeAPI": {
                "error_code": "TIMEOUT",
                "error_message": "Service timed out",
                "http_code": 504,
            }
        })
        with pytest.raises(ServiceError) as exc_info:
            FakeAPI().call("u1")
        err = exc_info.value
        assert err.service_name == "FakeAPI"
        assert err.error_code == "TIMEOUT"
        assert err.error_message == "Service timed out"
        assert err.http_code == 504
        clear_error_overrides()

    def test_error_recorded_in_call_log(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_error_overrides()
        set_error_overrides({
            "FakeAPI": {
                "error_code": "ERR",
                "error_message": "fail",
            }
        })
        with pytest.raises(ServiceError):
            FakeAPI().call("u1")
        log = get_call_log()
        assert len(log) == 1
        assert log[0]["error"]["error_code"] == "ERR"
        assert log[0]["result"] is None
        assert log[0]["mocked"] is True
        clear_error_overrides()

    def test_error_override_takes_precedence_over_mock(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_error_overrides()
        clear_mock_overrides()
        set_mock_overrides({"FakeAPI": 999.0})
        set_error_overrides({
            "FakeAPI": {"error_code": "E", "error_message": "m"}
        })
        with pytest.raises(ServiceError):
            FakeAPI().call("u1")
        clear_error_overrides()
        clear_mock_overrides()

    def test_no_error_override_returns_normally(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        clear_error_overrides()
        set_error_overrides({"SomeOtherService": {"error_code": "E", "error_message": "m"}})
        result = FakeAPI().call("u1")
        assert result == 42.0
        clear_error_overrides()

    def test_clear_error_overrides(self) -> None:
        set_mock_mode(True)
        clear_call_log()
        set_error_overrides({
            "FakeAPI": {"error_code": "E", "error_message": "m"}
        })
        clear_error_overrides()
        result = FakeAPI().call("u1")
        assert result == 42.0

    def test_mock_error_method(self) -> None:
        svc = FakeAPIWithError()
        err = svc.mock_error("u1")
        assert err is not None
        assert err.error_code == "NOT_FOUND"
        assert err.error_message == "User not found"
        assert err.http_code == 404

    def test_default_mock_error_returns_none(self) -> None:
        svc = FakeAPI()
        assert svc.mock_error("u1") is None

    def test_service_error_str_with_http_code(self) -> None:
        err = MockErrorResponse(error_code="E1", error_message="msg", http_code=503)
        exc = ServiceError("MyService", err)
        assert "[MyService] E1: msg" in str(exc)
        assert "(HTTP 503)" in str(exc)

    def test_service_error_str_without_http_code(self) -> None:
        err = MockErrorResponse(error_code="E1", error_message="msg")
        exc = ServiceError("MyService", err)
        assert "[MyService] E1: msg" in str(exc)
        assert "HTTP" not in str(exc)


class TestPydanticCoercion:
    """Test that dict overrides are coerced to Pydantic models when applicable."""

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

        class FetchUser(ExternalService):
            def execute(self, uid: str) -> UserInfo:
                pass  # type: ignore[return-value]

            def mock(self, uid: str) -> MockResponse:
                return MockResponse(data=UserInfo(name="Alice", age=30))

        # Without override, mock returns Pydantic model
        result = FetchUser().call("u1")
        assert isinstance(result, UserInfo)
        assert result.name == "Alice"

        # With dict override, should be coerced to Pydantic model
        clear_call_log()
        set_mock_overrides({"FetchUser": {"name": "Bob", "age": 25}})
        result = FetchUser().call("u1")
        assert isinstance(result, UserInfo)
        assert result.name == "Bob"
        assert result.age == 25

    def test_dict_override_not_coerced_for_non_pydantic(self) -> None:
        # FakeAPI returns a float, so dict override should stay as dict
        set_mock_overrides({"FakeAPI": {"score": 300}})
        result = FakeAPI().call("u1")
        assert result == {"score": 300}
        assert isinstance(result, dict)

    def test_scalar_override_not_coerced(self) -> None:
        pydantic = pytest.importorskip("pydantic")

        class Info(pydantic.BaseModel):
            name: str

        class FetchInfo(ExternalService):
            def execute(self) -> Info:
                pass  # type: ignore[return-value]

            def mock(self) -> MockResponse:
                return MockResponse(data=Info(name="test"))

        # Non-dict override should be left as-is
        set_mock_overrides({"FetchInfo": "raw_string"})
        result = FetchInfo().call()
        assert result == "raw_string"
