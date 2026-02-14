"""Async Odoo client wrapper.

Mirrors :class:`vodoo.client.OdooClient` with async methods.
"""

from typing import Any

from vodoo.aio.transport import (
    AsyncJSON2Transport,
    AsyncLegacyTransport,
    AsyncOdooTransport,
)
from vodoo.config import OdooConfig


class AsyncOdooClient:
    """Async Odoo client for external API access.

    Wraps an AsyncOdooTransport to provide a convenient async interface.
    Supports both legacy JSON-RPC (Odoo 14-18) and JSON-2 API (Odoo 19+).

    Can be used as an async context manager::

        async with AsyncOdooClient(config) as client:
            records = await client.search_read("res.partner", limit=5)
    """

    def __init__(
        self,
        config: OdooConfig,
        *,
        transport: AsyncOdooTransport | None = None,
        auto_detect: bool = True,
    ) -> None:
        """Initialize async Odoo client.

        Args:
            config: Odoo configuration
            transport: Explicit transport instance (skips auto-detection).
                       When *auto_detect* is ``True`` and no transport is
                       given, detection happens lazily on first use.
            auto_detect: If True, probe JSON-2 first then fall back to
                         legacy on first use. If False, use legacy directly.
        """
        self.config = config
        self.url = config.url.rstrip("/")
        self.db = config.database
        self.username = config.username
        self.password = config.password

        self._transport: AsyncOdooTransport | None = transport
        self._auto_detect = auto_detect

    async def _ensure_transport(self) -> AsyncOdooTransport:
        """Lazily initialise and return the transport."""
        if self._transport is not None:
            return self._transport

        if self._auto_detect:
            self._transport = await self._detect_transport()
        else:
            self._transport = AsyncLegacyTransport(
                url=self.url,
                database=self.db,
                username=self.username,
                password=self.password,
            )
        return self._transport

    @property
    def transport(self) -> AsyncOdooTransport:
        """The underlying transport (raises if not yet initialised)."""
        if self._transport is None:
            msg = (
                "Transport not initialised. Use the client in an async context or "
                "call an async method first."
            )
            raise RuntimeError(msg)
        return self._transport

    @property
    def is_json2(self) -> bool:
        """Whether the client is using the JSON-2 API (Odoo 19+)."""
        return isinstance(self._transport, AsyncJSON2Transport)

    async def _detect_transport(self) -> AsyncOdooTransport:
        """Auto-detect Odoo version and return appropriate async transport."""
        json2 = AsyncJSON2Transport(
            url=self.url,
            database=self.db,
            username=self.username,
            password=self.password,
        )
        try:
            await json2.authenticate()
            return json2
        except Exception:
            await json2.close()
            return AsyncLegacyTransport(
                url=self.url,
                database=self.db,
                username=self.username,
                password=self.password,
            )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._transport is not None:
            await self._transport.close()

    async def __aenter__(self) -> "AsyncOdooClient":
        await self._ensure_transport()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    @property
    def uid(self) -> int:
        """Get authenticated user ID (transport must be initialised)."""
        transport = self.transport
        if transport._uid is None:
            msg = "Not yet authenticated. Call an async method first."
            raise RuntimeError(msg)
        return transport._uid

    async def get_uid(self) -> int:
        """Get authenticated user ID, authenticating if needed."""
        transport = await self._ensure_transport()
        return await transport.get_uid()

    async def execute(
        self,
        model: str,
        method: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a method on an Odoo model."""
        transport = await self._ensure_transport()
        return await transport.execute_kw(model, method, list(args), kwargs or None)

    async def execute_sudo(
        self,
        model: str,
        method: str,
        user_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a method as another user using sudo."""
        if "context" not in kwargs:
            kwargs["context"] = {}
        kwargs["context"]["sudo_user_id"] = user_id
        return await self.execute(model, method, *args, **kwargs)

    async def search(
        self,
        model: str,
        domain: list[Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[int]:
        """Search for records."""
        transport = await self._ensure_transport()
        return await transport.search(model, domain, limit, offset, order)

    async def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records by IDs."""
        transport = await self._ensure_transport()
        return await transport.read(model, ids, fields)

    async def search_read(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search and read records in one call."""
        transport = await self._ensure_transport()
        return await transport.search_read(model, domain, fields, limit, offset, order)

    async def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        """Create a new record."""
        transport = await self._ensure_transport()
        return await transport.create(model, values, context)

    async def write(
        self,
        model: str,
        ids: list[int],
        values: dict[str, Any],
    ) -> bool:
        """Update records."""
        transport = await self._ensure_transport()
        return await transport.write(model, ids, values)

    async def unlink(
        self,
        model: str,
        ids: list[int],
    ) -> bool:
        """Delete records."""
        transport = await self._ensure_transport()
        return await transport.unlink(model, ids)

    async def name_search(
        self,
        model: str,
        name: str,
        domain: list[Any] | None = None,
        limit: int = 7,
    ) -> list[tuple[int, str]]:
        """Autocomplete search returning (id, display_name) pairs."""
        transport = await self._ensure_transport()
        return await transport.name_search(model, name, domain, limit)
