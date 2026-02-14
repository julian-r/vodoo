"""Async generic Odoo model operations."""

from typing import Any

from vodoo.aio.client import AsyncOdooClient


class AsyncGenericNamespace:
    """Async generic model operations for any Odoo model."""

    def __init__(self, client: AsyncOdooClient) -> None:
        self._client = client

    async def create(self, model: str, values: dict[str, Any]) -> int:
        """Create a new record."""
        return await self._client.create(model, values)

    async def update(self, model: str, record_id: int, values: dict[str, Any]) -> bool:
        """Update a record."""
        return await self._client.write(model, [record_id], values)

    async def delete(self, model: str, record_id: int) -> bool:
        """Delete a record."""
        return await self._client.unlink(model, [record_id])

    async def search(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search and read records."""
        return await self._client.search_read(
            model,
            domain=domain,
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def call(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Call a custom method on a model."""
        args = args or []
        kwargs = kwargs or {}
        return await self._client.execute(model, method, *args, **kwargs)
