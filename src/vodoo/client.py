"""Odoo JSON-RPC client wrapper."""

import json
import urllib.request
from typing import Any

from vodoo.config import OdooConfig


class OdooRPCError(Exception):
    """Exception raised for Odoo JSON-RPC errors."""

    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        """Initialize RPC error.

        Args:
            code: Error code from JSON-RPC response
            message: Error message
            data: Additional error data (debug info, traceback, etc.)

        """
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(f"[{code}] {message}")


class OdooClient:
    """Odoo JSON-RPC client for external API access."""

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

        # JSON-RPC endpoint
        self._endpoint = f"{self.url}/jsonrpc"

        # Authenticate and get uid
        self._uid: int | None = None

    def _jsonrpc_call(
        self,
        service: str,
        method: str,
        args: list[Any],
    ) -> Any:
        """Make a JSON-RPC 2.0 call to Odoo.

        Args:
            service: Service name ('common', 'object', 'db')
            method: Method name
            args: Arguments for the method

        Returns:
            Result from the JSON-RPC call

        Raises:
            OdooRPCError: If the RPC call returns an error

        """
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args,
            },
            "id": None,
        }

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read().decode("utf-8"))

        if "error" in result:
            error = result["error"]
            raise OdooRPCError(
                code=error.get("code", -1),
                message=error.get("message", "Unknown error"),
                data=error.get("data"),
            )

        return result.get("result")

    @property
    def uid(self) -> int:
        """Get authenticated user ID.

        Returns:
            User ID

        Raises:
            RuntimeError: If authentication fails

        """
        if self._uid is None:
            result = self._jsonrpc_call(
                "common",
                "authenticate",
                [self.db, self.username, self.password, {}],
            )
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
        return self._jsonrpc_call(
            "object",
            "execute_kw",
            [self.db, self.uid, self.password, model, method, list(args), kwargs],
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
        kwargs: dict[str, Any] = {}
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if offset > 0:
            kwargs["offset"] = offset
        if order is not None:
            kwargs["order"] = order

        result: list[dict[str, Any]] = self._jsonrpc_call(
            "object",
            "execute_kw",
            [self.db, self.uid, self.password, model, "search_read", [domain or []], kwargs],
        )
        return result

    def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        """Create a new record.

        Args:
            model: Odoo model name
            values: Field values for the new record
            context: Optional context dict (e.g., {'default_project_id': 10})

        Returns:
            ID of created record

        """
        kwargs: dict[str, Any] = {}
        if context:
            kwargs["context"] = context

        result: int = self._jsonrpc_call(
            "object",
            "execute_kw",
            [self.db, self.uid, self.password, model, "create", [values], kwargs],
        )
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

    def unlink(
        self,
        model: str,
        ids: list[int],
    ) -> bool:
        """Delete records.

        Args:
            model: Odoo model name
            ids: List of record IDs to delete

        Returns:
            True if successful

        """
        result: bool = self.execute(model, "unlink", ids)
        return result
