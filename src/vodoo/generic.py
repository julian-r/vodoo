"""Generic Odoo model operations."""

from typing import Any

from vodoo.client import OdooClient


class GenericNamespace:
    """Generic model operations for any Odoo model."""

    def __init__(self, client: OdooClient) -> None:
        self._client = client

    def create(self, model: str, values: dict[str, Any]) -> int:
        """Create a new record.

        Args:
            model: Model name (e.g., 'product.template')
            values: Dictionary of field values

        Returns:
            ID of created record

        Examples:
            >>> ns.create('res.partner', {'name': 'John Doe', 'email': 'john@example.com'})
            42

        """
        return self._client.create(model, values)

    def update(self, model: str, record_id: int, values: dict[str, Any]) -> bool:
        """Update a record.

        Args:
            model: Model name
            record_id: Record ID
            values: Dictionary of field values to update

        Returns:
            True if successful

        Examples:
            >>> ns.update('res.partner', 42, {'phone': '+1234567890'})
            True

        """
        return self._client.write(model, [record_id], values)

    def delete(self, model: str, record_id: int) -> bool:
        """Delete a record.

        Args:
            model: Model name
            record_id: Record ID

        Returns:
            True if successful

        Examples:
            >>> ns.delete('res.partner', 42)
            True

        """
        return self._client.unlink(model, [record_id])

    def search(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search and read records.

        Args:
            model: Model name
            domain: Search domain
            fields: Fields to fetch
            limit: Maximum number of records
            offset: Number of records to skip
            order: Sort order

        Returns:
            List of record dictionaries

        Examples:
            >>> ns.search('res.partner', [['name', 'ilike', 'john']])
            [{'id': 42, 'name': 'John Doe', ...}]

        """
        return self._client.search_read(
            model,
            domain=domain,
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
        )

    def call(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Call a custom method on a model.

        Args:
            model: Model name
            method: Method name
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Method result

        Examples:
            >>> ns.call('res.partner', 'name_search', args=['Acme'])
            [(1, 'Acme Corp'), (2, 'Acme Ltd')]

        """
        args = args or []
        kwargs = kwargs or {}

        return self._client.execute(model, method, *args, **kwargs)
