"""Async Odoo JSON-RPC transport abstraction.
- AsyncLegacyTransport: Odoo 14-18 using POST /jsonrpc with service/method/args envelope
- AsyncJSON2Transport: Odoo 19+ using POST /json/2/<model>/<method> with bearer token auth
The convenience methods on the base class and the concrete transport implementations
intentionally duplicate their sync counterparts.  This is a deliberate trade-off:
every alternative (``unasync``, code generation, runtime indirection) adds build or
type-system complexity that outweighs the cost of ~260 lines of mechanical duplication
in a library of this size.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx

from vodoo.exceptions import AuthenticationError, TransportError, transport_error_from_data
from vodoo.transport import (
    _RETRYABLE_METHODS,
    DEFAULT_RETRY,
    RetryConfig,
    _build_json2_body,
    _parse_json2_response,
    _parse_name_search,
)


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
        retry: RetryConfig | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.database = database.strip()
        self.username = username.strip()
        self.password = password.strip()
        self.timeout = timeout
        self.retry = retry or DEFAULT_RETRY
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

    def _is_retryable(self, method: str, exc: Exception) -> bool:
        """Check if a failed call should be retried."""
        if method not in _RETRYABLE_METHODS:
            return False
        return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout))

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
        call_args = [self.database, uid, self.password, model, method, args, kwargs or {}]
        last_exc: Exception | None = None
        for attempt in range(self.retry.max_retries + 1):
            try:
                return await self.call_service("object", "execute_kw", call_args)
            except Exception as exc:
                last_exc = exc
                if attempt < self.retry.max_retries and self._is_retryable(method, exc):
                    await asyncio.sleep(self.retry.delay(attempt))
                    continue
                raise
        raise last_exc  # type: ignore[misc]  # unreachable but satisfies mypy

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

        try:
            records = await self.search_read(
                "res.users",
                domain=[["login", "=", self.username]],
                fields=["id"],
                limit=1,
            )
        except TransportError as e:
            raise AuthenticationError(
                f"Authentication failed — API key may be invalid or lacks access: {e}"
            ) from e
        if not records:
            raise AuthenticationError(
                f"Authentication failed — user '{self.username}' not found. "
                "If using an API key, ensure it belongs to this user."
            )
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
        last_exc: Exception | None = None
        for attempt in range(self.retry.max_retries + 1):
            try:
                return await self._request(model, method, body)
            except Exception as exc:
                last_exc = exc
                if attempt < self.retry.max_retries and self._is_retryable(method, exc):
                    await asyncio.sleep(self.retry.delay(attempt))
                    continue
                raise
        raise last_exc  # type: ignore[misc]  # unreachable but satisfies mypy

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
