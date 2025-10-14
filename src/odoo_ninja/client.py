"""Odoo XML-RPC client wrapper."""

import xmlrpc.client
from typing import Any

from odoo_ninja.config import OdooConfig


class OdooClient:
    """Odoo XML-RPC client for external API access."""

    def __init__(self, config: OdooConfig) -> None:
        """Initialize Odoo client.

        Args:
            config: Odoo configuration

        """
        self.config = config
        self.url = config.url.rstrip("/")
        self.db = config.database
        self.username = config.username
        self.password = config.password

        # XML-RPC endpoints
        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

        # Authenticate and get uid
        self._uid: int | None = None

    @property
    def uid(self) -> int:
        """Get authenticated user ID.

        Returns:
            User ID

        Raises:
            RuntimeError: If authentication fails

        """
        if self._uid is None:
            result = self.common.authenticate(self.db, self.username, self.password, {})
            if not isinstance(result, int) or result <= 0:
                msg = "Authentication failed"
                raise RuntimeError(msg)
            self._uid = result
        return self._uid

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
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            method,
            args,
            kwargs,
        )

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
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Method result

        """
        # Add context with sudo user
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
        """Search for records.

        Args:
            model: Odoo model name
            domain: Search domain
            limit: Maximum number of records
            offset: Number of records to skip
            order: Sort order

        Returns:
            List of record IDs

        """
        kwargs: dict[str, Any] = {}
        if limit is not None:
            kwargs["limit"] = limit
        if offset > 0:
            kwargs["offset"] = offset
        if order is not None:
            kwargs["order"] = order

        result: list[int] = self.execute(model, "search", domain or [], **kwargs)
        return result

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records by IDs.

        Args:
            model: Odoo model name
            ids: List of record IDs
            fields: List of field names to read (None = all fields)

        Returns:
            List of record dictionaries

        """
        # For read, fields should be passed as a positional argument (list), not in kwargs
        if fields is not None:
            result: list[dict[str, Any]] = self.execute(model, "read", ids, fields)
        else:
            result = self.execute(model, "read", ids)
        return result

    def search_read(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search and read records in one call.

        Args:
            model: Odoo model name
            domain: Search domain
            fields: List of field names to read
            limit: Maximum number of records
            offset: Number of records to skip
            order: Sort order

        Returns:
            List of record dictionaries

        """
        # For search_read, we need to pass domain as positional arg and
        # fields/limit/offset/order as kwargs with specific names
        kwargs: dict[str, Any] = {}
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if offset > 0:
            kwargs["offset"] = offset
        if order is not None:
            kwargs["order"] = order

        # Use execute_kw which properly handles search_read parameters
        raw_result = self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            "search_read",
            [domain or []],  # domain as positional argument
            kwargs,  # fields, limit, offset, order as kwargs
        )
        result: list[dict[str, Any]] = raw_result  # type: ignore[assignment]
        return result

    def create(
        self,
        model: str,
        values: dict[str, Any],
    ) -> int:
        """Create a new record.

        Args:
            model: Odoo model name
            values: Field values for the new record

        Returns:
            ID of created record

        """
        result: int = self.execute(model, "create", values)
        return result

    def write(
        self,
        model: str,
        ids: list[int],
        values: dict[str, Any],
    ) -> bool:
        """Update records.

        Args:
            model: Odoo model name
            ids: List of record IDs to update
            values: Field values to update

        Returns:
            True if successful

        """
        result: bool = self.execute(model, "write", ids, values)
        return result
