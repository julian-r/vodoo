"""Vodoo — Python library and CLI for Odoo.

Quick start as a library::

    from vodoo import OdooClient, OdooConfig

    config = OdooConfig(
        url="https://my-instance.odoo.com",
        database="mydb",
        username="bot@example.com",
        password="secret",
    )
    client = OdooClient(config)

    # Use the high-level domain helpers …
    from vodoo.helpdesk import list_tickets
    tickets = list_tickets(client, limit=10)

    # … or the generic client directly
    partners = client.search_read("res.partner", fields=["name", "email"], limit=5)
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("vodoo")
except PackageNotFoundError:
    # Editable install without a tag, or running from source checkout
    __version__ = "0.0.0.dev0"

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
    RecordOperationError,
    TransportError,
    VodooError,
)

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "FieldParsingError",
    "OdooAccessDeniedError",
    "OdooAccessError",
    "OdooClient",
    "OdooConfig",
    "OdooMissingError",
    "OdooUserError",
    "OdooValidationError",
    "RecordNotFoundError",
    "RecordOperationError",
    "TransportError",
    "VodooError",
]
