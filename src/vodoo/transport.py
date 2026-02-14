"""Odoo JSON-RPC transport abstraction.

Provides two implementations:
- LegacyTransport: Odoo 14-18 using POST /jsonrpc with service/method/args envelope
- JSON2Transport: Odoo 19+ using POST /json/2/<model>/<method> with bearer token auth

The factory function `make_transport()` auto-detects the Odoo version.
"""

import json
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


class OdooTransportError(Exception):
    """Base exception for transport-level errors."""

    def __init__(self, message: str, code: int = -1, data: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(f"[{code}] {message}")


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
            OdooTransportError: If authentication fails.
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
            OdooTransportError: On RPC/HTTP errors.
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
            OdooTransportError: On RPC/HTTP errors.
        """

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
            raise OdooTransportError("Authentication failed", code=401)
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
        return self.call_service(
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

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/jsonrpc",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))

        if "error" in result:
            error = result["error"]
            raise OdooTransportError(
                message=error.get("message", "Unknown error"),
                code=error.get("code", -1),
                data=error.get("data"),
            )

        return result.get("result")


class JSON2Transport(OdooTransport):
    """Odoo 19+ JSON-2 API transport.

    Uses POST /json/2/<model>/<method> with bearer token auth.
    """

    def authenticate(self) -> int:
        if self._uid is not None:
            return self._uid

        # JSON-2 authenticates by looking up the current user via search_read
        records = self.search_read(
            "res.users",
            domain=[["login", "=", self.username]],
            fields=["id"],
            limit=1,
        )
        if not records:
            raise OdooTransportError("Authentication failed — user not found", code=401)
        uid = records[0].get("id")
        if not isinstance(uid, int):
            raise OdooTransportError("Authentication failed — invalid user ID", code=401)
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
        return self._request(model, method, body)

    def call_service(
        self,
        service: str,  # noqa: ARG002
        method: str,  # noqa: ARG002
        args: list[Any],  # noqa: ARG002
    ) -> Any:
        # JSON-2 doesn't have a service endpoint; fall back to legacy for service calls
        # This is only used for things like version_info which aren't model methods
        raise OdooTransportError(
            "call_service is not supported on JSON-2 transport; use execute_kw",
            code=-1,
        )

    def _request(self, model: str, method: str, body: dict[str, Any]) -> Any:
        """Send a JSON-2 API request."""
        endpoint = f"{self.url}/json/2/{model}/{method}"

        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"bearer {self.password}",
                "User-Agent": "Vodoo",
            },
        )
        if self.database:
            request.add_header("X-Odoo-Database", self.database)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                resp_data = response.read()
        except urllib.error.HTTPError as e:
            # Try to parse error body
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                msg = err_body.get("message", f"HTTP {e.code}")
            except Exception:
                msg = f"HTTP {e.code}"
            raise OdooTransportError(msg, code=e.code) from e

        if not resp_data:
            return None

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


def make_transport(
    url: str,
    database: str,
    username: str,
    password: str,
    *,
    timeout: int = 30,
) -> OdooTransport:
    """Auto-detect Odoo version and return the appropriate transport.

    Probes the JSON-2 endpoint first (Odoo 19+); falls back to legacy JSON-RPC.

    Args:
        url: Odoo instance URL
        database: Database name
        username: Username
        password: Password or API key
        timeout: Request timeout in seconds

    Returns:
        OdooTransport instance (JSON2Transport or LegacyTransport)
    """
    json2 = JSON2Transport(
        url=url,
        database=database,
        username=username,
        password=password,
        timeout=timeout,
    )
    try:
        json2.authenticate()
        return json2
    except Exception:
        return LegacyTransport(
            url=url,
            database=database,
            username=username,
            password=password,
            timeout=timeout,
        )


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
    elif method not in ("name_search", "fields_get") and args and isinstance(args[0], list):
        # Generic method call — pass ids if first arg is a list
        body["ids"] = args[0]

    if kwargs:
        body.update(kwargs)
        # Remap 'args' kwarg to 'domain' for JSON-2 (used by name_search)
        if "args" in body:
            body["domain"] = body.pop("args")

    return body


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
