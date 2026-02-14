"""Async generic Odoo model operations."""

from typing import Any

from vodoo.aio.client import AsyncOdooClient


async def create_record(
    client: AsyncOdooClient,
    model: str,
    values: dict[str, Any],
) -> int:
    """Create a new record."""
    return await client.create(model, values)


async def update_record(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    values: dict[str, Any],
) -> bool:
    """Update a record."""
    return await client.write(model, [record_id], values)


async def delete_record(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
) -> bool:
    """Delete a record."""
    return await client.unlink(model, [record_id])


async def search_records(
    client: AsyncOdooClient,
    model: str,
    domain: list[Any] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    order: str | None = None,
) -> list[dict[str, Any]]:
    """Search and read records."""
    return await client.search_read(
        model,
        domain=domain,
        fields=fields,
        limit=limit,
        offset=offset,
        order=order,
    )


async def call_method(
    client: AsyncOdooClient,
    model: str,
    method: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> Any:
    """Call a custom method on a model."""
    args = args or []
    kwargs = kwargs or {}
    return await client.execute(model, method, *args, **kwargs)
