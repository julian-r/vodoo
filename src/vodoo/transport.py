"""Odoo JSON-RPC transport abstraction.

Provides two implementations:
- LegacyTransport: Odoo 14-18 using POST /jsonrpc with service/method/args envelope
- JSON2Transport: Odoo 19+ using POST /json/2/<model>/<method> with bearer token auth
"""

import json
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from vodoo.exceptions import AuthenticationError, TransportError, transport_error_from_data

# Retry settings for transient network errors
_RETRY_COUNT = 2
_RETRY_BACKOFF = 0.5  # seconds
_RETRYABLE_METHODS = frozenset(
    {
        "search",
        "search_read",
        "read",
        "fields_get",
        "name_search",
    }
)


class OdooTransport(ABC):
    """Abstract base for Odoo RPC transports.

    Each transport knows how to authenticate, call model methods, and perform
    CRUD operations. The public API is identical regardless of the underlying
    protocol (legacy JSON-RPC or JSON-2 REST).
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
        self._http = httpx.Client(timeout=timeout)

    @property
    def uid(self) -> int:
        """Get authenticated user ID, authenticating if needed."""
        if self._uid is None:
            self._uid = self.authenticate()
        return self._uid

    @abstractmethod
    def authenticate(self) -> int:
        """Authenticate and return the user ID.

        Raises:
            AuthenticationError: If authentication fails.
        """

    @abstractmethod
    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a method on an Odoo model (execute_kw equivalent).

        Args:
            model: Odoo model name (e.g., 'project.task')
            method: Method name (e.g., 'search_read')
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Method result

        Raises:
            TransportError: On RPC/HTTP errors.
        """

    @abstractmethod
    def call_service(
        self,
        service: str,
        method: str,
        args: list[Any],
    ) -> Any:
        """Call a JSON-RPC service method (e.g. common/authenticate).

        Args:
            service: Service name ('common', 'object', 'db')
            method: Method name
            args: Arguments

        Returns:
            Result

        Raises:
            TransportError: On RPC/HTTP errors.
        """

    def _is_retryable(self, method: str, exc: Exception) -> bool:
        """Check if a failed call should be retried."""
        if method not in _RETRYABLE_METHODS:
            return False
        return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout))

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    # -- Convenience helpers (built on top of execute_kw) --

    def search_read(
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
        result: list[dict[str, Any]] = self.execute_kw(model, "search_read", [domain or []], kw)
        return result

    def search(
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
        result: list[int] = self.execute_kw(model, "search", [domain or []], kw)
        return result

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records by IDs."""
        if fields is not None:
            result: list[dict[str, Any]] = self.execute_kw(model, "read", [ids, fields])
        else:
            result = self.execute_kw(model, "read", [ids])
        return result

    def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        """Create a record and return its ID."""
        kw: dict[str, Any] = {}
        if context:
            kw["context"] = context
        result = self.execute_kw(model, "create", [values], kw if kw else None)
        # JSON-2 returns a list of IDs (vals_list), unwrap single-record creates
        if isinstance(result, list) and len(result) == 1:
            return int(result[0])
        return int(result)

    def write(
        self,
        model: str,
        ids: list[int],
        values: dict[str, Any],
    ) -> bool:
        """Update records."""
        result: bool = self.execute_kw(model, "write", [ids, values])
        return result

    def unlink(
        self,
        model: str,
        ids: list[int],
    ) -> bool:
        """Delete records."""
        result: bool = self.execute_kw(model, "unlink", [ids])
        return result

    def name_search(
        self,
        model: str,
        name: str,
        domain: list[Any] | None = None,
        limit: int = 7,
    ) -> list[tuple[int, str]]:
        """Autocomplete search returning (id, display_name) pairs."""
        result = self.execute_kw(
            model,
            "name_search",
            [],
            {"name": name, "args": domain or [], "limit": limit},
        )
        return _parse_name_search(result)


class LegacyTransport(OdooTransport):
    """Odoo 14-18 legacy JSON-RPC transport.

    Uses POST /jsonrpc with service/method/args envelope.
    """

    def authenticate(self) -> int:
        if self._uid is not None:
            return self._uid

        result = self.call_service(
            "common",
            "authenticate",
            [self.database, self.username, self.password, {}],
        )
        if not isinstance(result, int) or result <= 0:
            raise AuthenticationError("Authentication failed")
        self._uid = result
        return self._uid

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        uid = self.uid
        call_args = [self.database, uid, self.password, model, method, args, kwargs or {}]
        last_exc: Exception | None = None
        for attempt in range(_RETRY_COUNT + 1):
            try:
                return self.call_service("object", "execute_kw", call_args)
            except Exception as exc:
                last_exc = exc
                if attempt < _RETRY_COUNT and self._is_retryable(method, exc):
                    time.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
        raise last_exc  # type: ignore[misc]  # unreachable but satisfies mypy

    def call_service(
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

        response = self._http.post(
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
            # Prefer the user-facing message from data when available
            if isinstance(err_data, dict) and err_data.get("message"):
                err_msg = err_data["message"]
            raise transport_error_from_data(err_msg, code=err_code, data=err_data)

        return result.get("result")


class JSON2Transport(OdooTransport):
    """Odoo 19+ JSON-2 API transport.

    Uses POST /json/2/<model>/<method> with bearer token auth.
    """

    def authenticate(self) -> int:
        if self._uid is not None:
            return self._uid

        # JSON-2 authenticates by looking up the current user via search_read
        try:
            records = self.search_read(
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

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        body = _build_json2_body(method, args, kwargs)
        last_exc: Exception | None = None
        for attempt in range(_RETRY_COUNT + 1):
            try:
                return self._request(model, method, body)
            except Exception as exc:
                last_exc = exc
                if attempt < _RETRY_COUNT and self._is_retryable(method, exc):
                    time.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
        raise last_exc  # type: ignore[misc]  # unreachable but satisfies mypy

    def call_service(
        self,
        service: str,  # noqa: ARG002
        method: str,  # noqa: ARG002
        args: list[Any],  # noqa: ARG002
    ) -> Any:
        # JSON-2 doesn't have a service endpoint; fall back to legacy for service calls
        # This is only used for things like version_info which aren't model methods
        raise TransportError(
            "call_service is not supported on JSON-2 transport; use execute_kw",
        )

    def _request(self, model: str, method: str, body: dict[str, Any]) -> Any:
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
            response = self._http.post(endpoint, json=body, headers=headers)
            response.raise_for_status()
            resp_data = response.content
        except httpx.HTTPStatusError as e:
            # Try to parse error body for structured Odoo error info
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


# -- Shared helpers -----------------------------------------------------------


def _build_json2_body(  # noqa: PLR0912
    method: str,
    args: list[Any],
    kwargs: dict[str, Any] | None,
) -> dict[str, Any]:
    """Map execute_kw arguments into a JSON-2 request body."""
    body: dict[str, Any] = {}

    # Methods where first arg is a domain
    if method in ("search_read", "search"):
        if args:
            body["domain"] = args[0]
    elif method == "read":
        if args:
            body["ids"] = args[0]
            if len(args) > 1:
                body["fields"] = args[1]
    elif method == "create":
        if args:
            val = args[0]
            # JSON-2 expects vals_list (a list of dicts), not a single dict
            body["vals_list"] = val if isinstance(val, list) else [val]
    elif method == "write":
        if args:
            body["ids"] = args[0]
            if len(args) > 1:
                body["vals"] = args[1]
    elif method == "unlink":
        if args:
            body["ids"] = args[0]
    elif args and isinstance(args[0], list) and all(isinstance(i, int) for i in args[0]):
        # Generic method call — pass as ids when first arg is a list of ints
        # (e.g., action_timer_start([42])). Other list-typed first args are
        # left for the caller to structure via kwargs.
        body["ids"] = args[0]

    if kwargs:
        body.update(kwargs)
        # Remap 'args' kwarg to 'domain' for JSON-2 (used by name_search)
        if "args" in body:
            body["domain"] = body.pop("args")

    return body


def _parse_json2_response(resp_data: bytes) -> Any:
    """Parse a JSON-2 response body."""
    raw = resp_data.decode("utf-8").strip()
    if raw in ("null", "false"):
        return None
    if raw == "true":
        return True

    # Try JSON parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Bare number
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        pass

    # Bare string
    return raw


def _parse_name_search(result: Any) -> list[tuple[int, str]]:
    """Parse Odoo's name_search result: [[id, "display_name"], ...]."""
    if not isinstance(result, list):
        return []
    pairs: list[tuple[int, str]] = []
    for pair in result:
        if isinstance(pair, list) and len(pair) >= 2:
            rec_id = pair[0]
            name = pair[1]
            if isinstance(rec_id, int) and isinstance(name, str):
                pairs.append((rec_id, name))
    return pairs
