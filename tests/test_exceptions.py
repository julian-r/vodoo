"""Unit tests for the Vodoo exception hierarchy.

Uses a mock OdooTransport so no live Odoo instance is needed.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from vodoo.client import OdooClient
from vodoo.config import OdooConfig
from vodoo.exceptions import (
    AuthenticationError,
    ConfigurationError,
    FieldParsingError,
    OdooAccessDeniedError,
    OdooAccessError,
    OdooMissingError,
    OdooUserError,
    OdooValidationError,
    RecordNotFoundError,
    TransportError,
    VodooError,
    transport_error_from_data,
)
from vodoo.transport import OdooTransport

# ── helpers ───────────────────────────────────────────────────────────────────


class MockTransport(OdooTransport):
    """Minimal in-memory transport for testing.

    ``execute_kw`` delegates to a callback so tests can control responses.
    """

    def __init__(self, *, execute_kw_fn: Any = None) -> None:
        super().__init__(
            url="https://mock.odoo.test",
            database="testdb",
            username="admin",
            password="secret",
        )
        self._uid = 1
        self._execute_kw_fn = execute_kw_fn or self._default_execute_kw

    def authenticate(self) -> int:
        return 1

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        return self._execute_kw_fn(model, method, args, kwargs)

    def call_service(
        self,
        service: str,  # noqa: ARG002
        method: str,  # noqa: ARG002
        args: list[Any],  # noqa: ARG002
    ) -> Any:
        return None

    @staticmethod
    def _default_execute_kw(
        model: str,  # noqa: ARG004
        method: str,  # noqa: ARG004
        args: list[Any],  # noqa: ARG004
        kwargs: dict[str, Any] | None,  # noqa: ARG004
    ) -> Any:
        return []


def _make_client(transport: OdooTransport) -> OdooClient:
    config = OdooConfig(
        url="https://mock.odoo.test",
        database="testdb",
        username="admin",
        password="secret",
    )
    return OdooClient(config, transport=transport)


# ── hierarchy ─────────────────────────────────────────────────────────────────


class TestExceptionHierarchy:
    """Every Vodoo exception must be catchable via VodooError."""

    def test_transport_error_is_vodoo_error(self) -> None:
        assert issubclass(TransportError, VodooError)

    def test_odoo_user_error_is_transport_error(self) -> None:
        assert issubclass(OdooUserError, TransportError)

    def test_odoo_access_error_is_user_error(self) -> None:
        assert issubclass(OdooAccessError, OdooUserError)

    def test_odoo_access_denied_is_user_error(self) -> None:
        assert issubclass(OdooAccessDeniedError, OdooUserError)

    def test_odoo_missing_error_is_user_error(self) -> None:
        assert issubclass(OdooMissingError, OdooUserError)

    def test_odoo_validation_error_is_user_error(self) -> None:
        assert issubclass(OdooValidationError, OdooUserError)

    def test_authentication_error_is_vodoo_error(self) -> None:
        assert issubclass(AuthenticationError, VodooError)

    def test_record_not_found_is_vodoo_error(self) -> None:
        assert issubclass(RecordNotFoundError, VodooError)

    def test_configuration_error_is_vodoo_error(self) -> None:
        assert issubclass(ConfigurationError, VodooError)

    def test_field_parsing_error_is_vodoo_error(self) -> None:
        assert issubclass(FieldParsingError, VodooError)

    def test_catch_all_via_vodoo_error(self) -> None:
        """Library consumers can catch everything with ``except VodooError``."""
        for exc in (
            TransportError("x"),
            OdooAccessError("x"),
            OdooValidationError("x"),
            AuthenticationError("x"),
            RecordNotFoundError("res.partner", 1),
            ConfigurationError("x"),
            FieldParsingError("x"),
        ):
            with pytest.raises(VodooError):
                raise exc


# ── transport_error_from_data mapping ─────────────────────────────────────────


class TestTransportErrorFromData:
    """``transport_error_from_data`` must return the most specific subclass."""

    def test_access_error(self) -> None:
        exc = transport_error_from_data(
            "no access",
            code=200,
            data={"name": "odoo.exceptions.AccessError", "message": "no access"},
        )
        assert isinstance(exc, OdooAccessError)
        assert isinstance(exc, OdooUserError)
        assert isinstance(exc, TransportError)

    def test_access_denied(self) -> None:
        exc = transport_error_from_data(
            "denied",
            code=200,
            data={"name": "odoo.exceptions.AccessDenied"},
        )
        assert isinstance(exc, OdooAccessDeniedError)

    def test_missing_error(self) -> None:
        exc = transport_error_from_data(
            "gone",
            code=200,
            data={"name": "odoo.exceptions.MissingError"},
        )
        assert isinstance(exc, OdooMissingError)

    def test_validation_error(self) -> None:
        exc = transport_error_from_data(
            "bad value",
            code=200,
            data={"name": "odoo.exceptions.ValidationError"},
        )
        assert isinstance(exc, OdooValidationError)

    def test_generic_user_error(self) -> None:
        exc = transport_error_from_data(
            "oops",
            code=200,
            data={"name": "odoo.exceptions.UserError"},
        )
        assert type(exc) is OdooUserError

    def test_unknown_name_falls_back_to_transport_error(self) -> None:
        exc = transport_error_from_data(
            "weird",
            code=500,
            data={"name": "odoo.exceptions.SomeFutureError"},
        )
        assert type(exc) is TransportError

    def test_no_data_falls_back_to_transport_error(self) -> None:
        exc = transport_error_from_data("fail", code=500, data=None)
        assert type(exc) is TransportError

    def test_attributes_preserved(self) -> None:
        data = {"name": "odoo.exceptions.AccessError", "debug": "traceback..."}
        exc = transport_error_from_data("msg", code=403, data=data)
        assert exc.code == 403
        assert exc.data == data
        assert "msg" in str(exc)


# ── RecordNotFoundError via mock transport ────────────────────────────────────


class TestRecordNotFoundError:
    """get_record / download_attachment must raise RecordNotFoundError."""

    def test_get_record_raises(self) -> None:
        transport = MockTransport(execute_kw_fn=lambda *_a, **_kw: [])
        client = _make_client(transport)

        from vodoo.base import get_record

        with pytest.raises(RecordNotFoundError) as exc_info:
            get_record(client, "res.partner", 99999)

        assert exc_info.value.model == "res.partner"
        assert exc_info.value.record_id == 99999

    def test_download_attachment_not_found(self) -> None:
        transport = MockTransport(execute_kw_fn=lambda *_a, **_kw: [])
        client = _make_client(transport)

        from vodoo.base import download_attachment

        with pytest.raises(RecordNotFoundError) as exc_info:
            download_attachment(client, 99999)

        assert exc_info.value.model == "ir.attachment"

    def test_catchable_as_vodoo_error(self) -> None:
        transport = MockTransport(execute_kw_fn=lambda *_a, **_kw: [])
        client = _make_client(transport)

        from vodoo.base import get_record

        with pytest.raises(VodooError):
            get_record(client, "res.partner", 99999)


# ── ConfigurationError via mock transport ─────────────────────────────────────


class TestConfigurationError:
    """message_post_sudo must raise ConfigurationError when no default user."""

    def test_no_default_user_raises(self) -> None:
        transport = MockTransport()
        config = OdooConfig(
            url="https://mock.odoo.test",
            database="testdb",
            username="admin",
            password="secret",
            default_user_id=None,
        )
        client = OdooClient(config, transport=transport)

        from vodoo.auth import message_post_sudo

        with pytest.raises(ConfigurationError):
            message_post_sudo(client, "res.partner", 1, "<p>hi</p>")


# ── FieldParsingError via mock transport ──────────────────────────────────────


class TestFieldParsingError:
    """parse_field_assignment must raise FieldParsingError on bad input."""

    def _make_client_with_fields(self) -> OdooClient:
        """Client whose transport returns field metadata for res.partner."""

        def execute_kw_fn(
            model: str,  # noqa: ARG001
            method: str,
            args: list[Any],  # noqa: ARG001
            kwargs: dict[str, Any] | None,  # noqa: ARG001
        ) -> Any:
            if method == "fields_get":
                return {"name": {"type": "char"}, "priority": {"type": "integer"}}
            if method == "read":
                # Return a record for compound-assignment tests
                return [{"id": 1, "name": "Test", "priority": 5}]
            return []

        return _make_client(MockTransport(execute_kw_fn=execute_kw_fn))

    def test_bad_format_raises(self) -> None:
        client = self._make_client_with_fields()

        from vodoo.base import parse_field_assignment

        with pytest.raises(FieldParsingError):
            parse_field_assignment(client, "res.partner", 1, "no-equals-sign")

    def test_bad_json_raises(self) -> None:
        client = self._make_client_with_fields()

        from vodoo.base import parse_field_assignment

        with pytest.raises(FieldParsingError):
            parse_field_assignment(client, "res.partner", 1, "name=json:{invalid")

    def test_compound_operator_non_numeric_raises(self) -> None:
        client = self._make_client_with_fields()

        from vodoo.base import parse_field_assignment

        with pytest.raises(FieldParsingError):
            parse_field_assignment(client, "res.partner", 1, "name+=hello")

    def test_division_by_zero_raises(self) -> None:
        client = self._make_client_with_fields()

        from vodoo.base import parse_field_assignment

        with pytest.raises(FieldParsingError):
            parse_field_assignment(client, "res.partner", 1, "priority/=0")

    def test_catchable_as_vodoo_error(self) -> None:
        client = self._make_client_with_fields()

        from vodoo.base import parse_field_assignment

        with pytest.raises(VodooError):
            parse_field_assignment(client, "res.partner", 1, "garbage")


# ── HTTPS config warning ──────────────────────────────────────────────────────


class TestHTTPSWarning:
    """OdooConfig must warn when the URL is not HTTPS."""

    def test_http_url_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            OdooConfig(
                url="http://insecure.example.com",
                database="db",
                username="u",
                password="p",
            )
        assert len(w) == 1
        assert "HTTPS" in str(w[0].message)

    def test_https_url_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            OdooConfig(
                url="https://secure.example.com",
                database="db",
                username="u",
                password="p",
            )
        assert len(w) == 0
