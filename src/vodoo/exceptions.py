"""Vodoo exception hierarchy.

All public exceptions inherit from :class:`VodooError` so that library
consumers can catch a single base class when desired.

The Odoo-server error classes (:class:`OdooUserError` and its subclasses)
mirror the hierarchy defined in ``odoo/exceptions.py`` on the server.
When the transport layer receives a JSON-RPC or JSON-2 error whose
``data.name`` matches a known Odoo exception class, it raises the
corresponding Vodoo exception so callers can handle specific failure
modes without parsing error strings.

Hierarchy overview::

    VodooError
    ├── ConfigurationError
    │   └── InsecureURLError
    ├── AuthenticationError
    ├── RecordNotFoundError
    ├── RecordOperationError
    ├── TransportError
    │   └── OdooUserError           ← odoo.exceptions.UserError
    │       ├── OdooAccessDeniedError    ← odoo.exceptions.AccessDenied
    │       ├── OdooAccessError     ← odoo.exceptions.AccessError
    │       ├── OdooMissingError    ← odoo.exceptions.MissingError
    │       └── OdooValidationError ← odoo.exceptions.ValidationError
    └── FieldParsingError
"""

from typing import Any


class VodooError(Exception):
    """Base exception for all Vodoo errors."""


# -- Configuration / connection ------------------------------------------------


class ConfigurationError(VodooError):
    """Raised when the configuration is invalid or incomplete."""


class InsecureURLError(ConfigurationError):
    """Raised when the Odoo URL does not use HTTPS."""


class AuthenticationError(VodooError):
    """Raised when authentication with the Odoo server fails."""


# -- Record operations ---------------------------------------------------------


class RecordNotFoundError(VodooError):
    """Raised when an expected Odoo record does not exist."""

    def __init__(self, model: str, record_id: int) -> None:
        self.model = model
        self.record_id = record_id
        super().__init__(f"Record {record_id} not found in {model}")


class RecordOperationError(VodooError):
    """Raised when a write/create/unlink operation fails."""


# -- Transport -----------------------------------------------------------------


class TransportError(VodooError):
    """Raised on JSON-RPC / HTTP transport failures.

    Carries the numeric error *code* and the raw *data* dict returned by
    the server so that callers can inspect details without string-parsing.
    """

    def __init__(
        self,
        message: str,
        code: int = -1,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.data = data or {}
        super().__init__(f"[{code}] {message}")


# -- Odoo server-side exceptions -----------------------------------------------
# These mirror ``odoo/exceptions.py`` and are raised when the transport layer
# can identify the Odoo exception class from the ``data.name`` field in the
# JSON-RPC error response (e.g. ``"odoo.exceptions.AccessError"``).


class OdooUserError(TransportError):
    """The server raised ``odoo.exceptions.UserError``.

    This is the generic Odoo end-user error — semantically a 400-class
    problem (bad request / invalid operation given the current state).
    """


class OdooAccessDeniedError(OdooUserError):
    """The server raised ``odoo.exceptions.AccessDenied``.

    Login or API-key authentication failed.
    """


class OdooAccessError(OdooUserError):
    """The server raised ``odoo.exceptions.AccessError``.

    The authenticated user lacks the required access rights (ACL / record
    rules) for the attempted operation.
    """


class OdooMissingError(OdooUserError):
    """The server raised ``odoo.exceptions.MissingError``.

    The record(s) referenced in the operation no longer exist.
    """


class OdooValidationError(OdooUserError):
    """The server raised ``odoo.exceptions.ValidationError``.

    A Python constraint or SQL constraint was violated during
    create/write.
    """


# Map from ``data["name"]`` values to exception classes.  The transport
# layer uses this to pick the most specific exception type.
ODOO_EXCEPTION_MAP: dict[str, type[TransportError]] = {
    "odoo.exceptions.UserError": OdooUserError,
    "odoo.exceptions.AccessDenied": OdooAccessDeniedError,
    "odoo.exceptions.AccessError": OdooAccessError,
    "odoo.exceptions.MissingError": OdooMissingError,
    "odoo.exceptions.ValidationError": OdooValidationError,
}


def transport_error_from_data(
    message: str,
    code: int = -1,
    data: dict[str, Any] | None = None,
) -> TransportError:
    """Create the most specific :class:`TransportError` subclass for *data*.

    Inspects ``data["name"]`` (set by Odoo's ``serialize_exception``) and
    returns an instance of the matching :class:`OdooUserError` subclass
    when possible, falling back to plain :class:`TransportError`.
    """
    if data:
        exc_name = data.get("name", "")
        cls = ODOO_EXCEPTION_MAP.get(exc_name, TransportError)
    else:
        cls = TransportError
    return cls(message, code=code, data=data)


# -- Field parsing -------------------------------------------------------------


class FieldParsingError(VodooError):
    """Raised when a ``field=value`` assignment cannot be parsed."""
