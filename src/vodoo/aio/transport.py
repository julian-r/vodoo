"""Async Odoo JSON-RPC transport abstraction.

Provides two async implementations:
- AsyncLegacyTransport: Odoo 14-18 using POST /jsonrpc with service/method/args envelope
- AsyncJSON2Transport: Odoo 19+ using POST /json/2/<model>/<method> with bearer token auth

Mirrors :mod:`vodoo.transport` but uses ``httpx.AsyncClient`` for non-blocking I/O.
"""

from abc import ABC, abstractmethod
from typing import Any

import httpx

from vodoo.exceptions import AuthenticationError, TransportError, transport_error_from_data
from vodoo.transport import _build_json2_body, _parse_json2_response, _parse_name_search


class AsyncOdooTransport(ABC):
    """Abstract base for async Odoo RPC transports.

    Mirrors :class:`vodoo.transport.OdooTransport` with async methods.
    """

    def __init__(
        self,
        url: str,
        database: str,
        username: str,
        password: str,
        *,
        timeout: int = 30,
    ) -> None:
        self.url = url.rstrip("/")
        self.database = database.strip()
        self.username = username.strip()
        self.password = password.strip()
        self.timeout = timeout
        self._uid: int | None = None
        self._http = httpx.AsyncClient(timeout=timeout)

    async def get_uid(self) -> int:
        """Get authenticated user ID, authenticating if needed."""
        if self._uid is None:
            self._uid = await self.authenticate()
        return self._uid

    @abstractmethod
    async def authenticate(self) -> int:
        """Authenticate and return the user ID.

        Raises:
            AuthenticationError: If authentication fails.
        """

    @abstractmethod
    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a method on an Odoo model (execute_kw equivalent)."""

    @abstractmethod
    async def call_service(
        self,
        service: str,
        method: str,
        args: list[Any],
    ) -> Any:
        """Call a JSON-RPC service method (e.g. common/authenticate)."""

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncOdooTransport":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # -- Convenience helpers (built on top of execute_kw) --

    async def search_read(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search and read records."""
        kw: dict[str, Any] = {}
        if fields is not None:
            kw["fields"] = fields
        if limit is not None:
            kw["limit"] = limit
        if offset > 0:
            kw["offset"] = offset
        if order is not None:
            kw["order"] = order
        result: list[dict[str, Any]] = await self.execute_kw(
            model, "search_read", [domain or []], kw
        )
        return result

    async def search(
        self,
        model: str,
        domain: list[Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[int]:
        """Search for record IDs."""
        kw: dict[str, Any] = {}
        if limit is not None:
            kw["limit"] = limit
        if offset > 0:
            kw["offset"] = offset
        if order is not None:
            kw["order"] = order
        result: list[int] = await self.execute_kw(model, "search", [domain or []], kw)
        return result

    async def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records by IDs."""
        if fields is not None:
            result: list[dict[str, Any]] = await self.execute_kw(model, "read", [ids, fields])
        else:
            result = await self.execute_kw(model, "read", [ids])
        return result

    async def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        """Create a record and return its ID."""
        kw: dict[str, Any] = {}
        if context:
            kw["context"] = context
        result = await self.execute_kw(model, "create", [values], kw if kw else None)
        if isinstance(result, list) and len(result) == 1:
            return int(result[0])
        return int(result)

    async def write(
        self,
        model: str,
        ids: list[int],
        values: dict[str, Any],
    ) -> bool:
        """Update records."""
        result: bool = await self.execute_kw(model, "write", [ids, values])
        return result

    async def unlink(
        self,
        model: str,
        ids: list[int],
    ) -> bool:
        """Delete records."""
        result: bool = await self.execute_kw(model, "unlink", [ids])
        return result

    async def name_search(
        self,
        model: str,
        name: str,
        domain: list[Any] | None = None,
        limit: int = 7,
    ) -> list[tuple[int, str]]:
        """Autocomplete search returning (id, display_name) pairs."""
        result = await self.execute_kw(
            model,
            "name_search",
            [],
            {"name": name, "args": domain or [], "limit": limit},
        )
        return _parse_name_search(result)


class AsyncLegacyTransport(AsyncOdooTransport):
    """Async Odoo 14-18 legacy JSON-RPC transport."""

    async def authenticate(self) -> int:
        if self._uid is not None:
            return self._uid

        result = await self.call_service(
            "common",
            "authenticate",
            [self.database, self.username, self.password, {}],
        )
        if not isinstance(result, int) or result <= 0:
            raise AuthenticationError("Authentication failed")
        self._uid = result
        return self._uid

    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        uid = await self.get_uid()
        return await self.call_service(
            "object",
            "execute_kw",
            [
                self.database,
                uid,
                self.password,
                model,
                method,
                args,
                kwargs or {},
            ],
        )

    async def call_service(
        self,
        service: str,
        method: str,
        args: list[Any],
    ) -> Any:
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

        response = await self._http.post(
            f"{self.url}/jsonrpc",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            error = result["error"]
            err_code = error.get("code", -1)
            err_data = error.get("data")
            err_msg = error.get("message", "Unknown error")
            if isinstance(err_data, dict) and err_data.get("message"):
                err_msg = err_data["message"]
            raise transport_error_from_data(err_msg, code=err_code, data=err_data)

        return result.get("result")


class AsyncJSON2Transport(AsyncOdooTransport):
    """Async Odoo 19+ JSON-2 API transport."""

    async def authenticate(self) -> int:
        if self._uid is not None:
            return self._uid

        records = await self.search_read(
            "res.users",
            domain=[["login", "=", self.username]],
            fields=["id"],
            limit=1,
        )
        if not records:
            raise AuthenticationError("Authentication failed — user not found")
        uid = records[0].get("id")
        if not isinstance(uid, int):
            raise AuthenticationError("Authentication failed — invalid user ID")
        self._uid = uid
        return self._uid

    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        body = _build_json2_body(method, args, kwargs)
        return await self._request(model, method, body)

    async def call_service(
        self,
        service: str,  # noqa: ARG002
        method: str,  # noqa: ARG002
        args: list[Any],  # noqa: ARG002
    ) -> Any:
        raise TransportError(
            "call_service is not supported on JSON-2 transport; use execute_kw",
        )

    async def _request(self, model: str, method: str, body: dict[str, Any]) -> Any:
        """Send a JSON-2 API request."""
        endpoint = f"{self.url}/json/2/{model}/{method}"

        headers: dict[str, str] = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"bearer {self.password}",
            "User-Agent": "Vodoo",
        }
        if self.database:
            headers["X-Odoo-Database"] = self.database

        try:
            response = await self._http.post(endpoint, json=body, headers=headers)
            response.raise_for_status()
            resp_data = response.content
        except httpx.HTTPStatusError as e:
            err_data: dict[str, Any] | None = None
            try:
                err_body = e.response.json()
                msg = err_body.get("message", f"HTTP {e.response.status_code}")
                if isinstance(err_body, dict):
                    err_data = err_body.get("data") or err_body
            except Exception:
                msg = f"HTTP {e.response.status_code}"
            raise transport_error_from_data(msg, code=e.response.status_code, data=err_data) from e

        if not resp_data:
            return None

        return _parse_json2_response(resp_data)


async def make_async_transport(
    url: str,
    database: str,
    username: str,
    password: str,
    *,
    timeout: int = 30,
) -> AsyncOdooTransport:
    """Auto-detect Odoo version and return the appropriate async transport.

    Probes the JSON-2 endpoint first (Odoo 19+); falls back to legacy JSON-RPC.
    """
    json2 = AsyncJSON2Transport(
        url=url,
        database=database,
        username=username,
        password=password,
        timeout=timeout,
    )
    try:
        await json2.authenticate()
        return json2
    except Exception:
        await json2.close()
        return AsyncLegacyTransport(
            url=url,
            database=database,
            username=username,
            password=password,
            timeout=timeout,
        )
