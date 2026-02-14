"""Odoo client wrapper.

Provides OdooClient which delegates to an OdooTransport (legacy JSON-RPC or JSON-2).
The transport is auto-detected based on the Odoo version unless explicitly specified.
"""

from typing import Any

from vodoo.config import OdooConfig
from vodoo.transport import (
    JSON2Transport,
    LegacyTransport,
    OdooTransport,
)


class OdooClient:
    """Odoo client for external API access.

    Wraps an OdooTransport to provide a convenient interface for Odoo operations.
    Supports both legacy JSON-RPC (Odoo 14-18) and JSON-2 API (Odoo 19+).
    """

    def __init__(
        self,
        config: OdooConfig,
        *,
        transport: OdooTransport | None = None,
        auto_detect: bool = True,
    ) -> None:
        """Initialize Odoo client.

        Args:
            config: Odoo configuration
            transport: Explicit transport instance (skips auto-detection)
            auto_detect: If True and no transport given, probe JSON-2 first then
                         fall back to legacy. If False, use legacy directly.
        """
        self.config = config
        self.url = config.url.rstrip("/")
        self.db = config.database
        self.username = config.username
        self.password = config.password

        if transport is not None:
            self._transport = transport
        elif auto_detect:
            self._transport = self._detect_transport()
        else:
            self._transport = LegacyTransport(
                url=self.url,
                database=self.db,
                username=self.username,
                password=self.password,
            )

    @property
    def transport(self) -> OdooTransport:
        """The underlying transport."""
        return self._transport

    @property
    def is_json2(self) -> bool:
        """Whether the client is using the JSON-2 API (Odoo 19+)."""
        return isinstance(self._transport, JSON2Transport)

    def _detect_transport(self) -> OdooTransport:
        """Auto-detect Odoo version and return appropriate transport."""
        json2 = JSON2Transport(
            url=self.url,
            database=self.db,
            username=self.username,
            password=self.password,
        )
        try:
            json2.authenticate()
            return json2
        except Exception:
            json2.close()
            return LegacyTransport(
                url=self.url,
                database=self.db,
                username=self.username,
                password=self.password,
            )

    @property
    def uid(self) -> int:
        """Get authenticated user ID."""
        return self._transport.uid

    def execute(
        self,
        model: str,
        method: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a method on an Odoo model.

        Args:
            model: Odoo model name (e.g., 'helpdesk.ticket')
            method: Method name (e.g., 'search', 'read')
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Method result
        """
        return self._transport.execute_kw(model, method, list(args), kwargs or None)

    def execute_sudo(
        self,
        model: str,
        method: str,
        user_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a method as another user using sudo.

        Args:
            model: Odoo model name
            method: Method name
            user_id: User ID to execute as
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Method result
        """
        if "context" not in kwargs:
            kwargs["context"] = {}
        kwargs["context"]["sudo_user_id"] = user_id
        return self.execute(model, method, *args, **kwargs)

    def search(
        self,
        model: str,
        domain: list[Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[int]:
        """Search for records."""
        return self._transport.search(model, domain, limit, offset, order)

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records by IDs."""
        return self._transport.read(model, ids, fields)

    def search_read(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search and read records in one call."""
        return self._transport.search_read(model, domain, fields, limit, offset, order)

    def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        """Create a new record."""
        return self._transport.create(model, values, context)

    def write(
        self,
        model: str,
        ids: list[int],
        values: dict[str, Any],
    ) -> bool:
        """Update records."""
        return self._transport.write(model, ids, values)

    def unlink(
        self,
        model: str,
        ids: list[int],
    ) -> bool:
        """Delete records."""
        return self._transport.unlink(model, ids)

    def name_search(
        self,
        model: str,
        name: str,
        domain: list[Any] | None = None,
        limit: int = 7,
    ) -> list[tuple[int, str]]:
        """Autocomplete search returning (id, display_name) pairs."""
        return self._transport.name_search(model, name, domain, limit)
