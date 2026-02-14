"""Generic Odoo model operations."""

from typing import Any

from vodoo.client import OdooClient


def create_record(
    client: OdooClient,
    model: str,
    values: dict[str, Any],
) -> int:
    """Create a new record.

    Args:
        client: Odoo client
        model: Model name (e.g., 'product.template')
        values: Dictionary of field values

    Returns:
        ID of created record

    Examples:
        >>> create_record(client, 'res.partner', {'name': 'John Doe', 'email': 'john@example.com'})
        42

    """
    return client.create(model, values)


def update_record(
    client: OdooClient,
    model: str,
    record_id: int,
    values: dict[str, Any],
) -> bool:
    """Update a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        values: Dictionary of field values to update

    Returns:
        True if successful

    Examples:
        >>> update_record(client, 'res.partner', 42, {'phone': '+1234567890'})
        True

    """
    return client.write(model, [record_id], values)


def delete_record(
    client: OdooClient,
    model: str,
    record_id: int,
) -> bool:
    """Delete a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID

    Returns:
        True if successful

    Examples:
        >>> delete_record(client, 'res.partner', 42)
        True

    """
    return client.unlink(model, [record_id])


def search_records(
    client: OdooClient,
    model: str,
    domain: list[Any] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    order: str | None = None,
) -> list[dict[str, Any]]:
    """Search and read records.

    Args:
        client: Odoo client
        model: Model name
        domain: Search domain
        fields: Fields to fetch
        limit: Maximum number of records
        offset: Number of records to skip
        order: Sort order

    Returns:
        List of record dictionaries

    Examples:
        >>> search_records(client, 'res.partner', [['name', 'ilike', 'john']])
        [{'id': 42, 'name': 'John Doe', ...}]

    """
    return client.search_read(
        model,
        domain=domain,
        fields=fields,
        limit=limit,
        offset=offset,
        order=order,
    )


def call_method(
    client: OdooClient,
    model: str,
    method: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> Any:
    """Call a custom method on a model.

    Args:
        client: Odoo client
        model: Model name
        method: Method name
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Method result

    Examples:
        >>> call_method(client, 'res.partner', 'name_search', args=['Acme'])
        [(1, 'Acme Corp'), (2, 'Acme Ltd')]

    """
    args = args or []
    kwargs = kwargs or {}

    return client.execute(model, method, *args, **kwargs)
