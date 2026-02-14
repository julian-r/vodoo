"""Odoo client wrapper with domain namespaces.
The transport is auto-detected based on the Odoo version unless explicitly specified.
Some methods (``search``, ``read``, ``search_read``, ``unlink``, ``name_search``)
are pure pass-throughs to the transport.  They exist so callers always use
``client.method()`` — mixing ``client.create()`` (which adds ``process_values``)
with ``client.transport.search()`` would be a confusing API surface.
"""

from typing import Any

from vodoo.config import OdooConfig
from vodoo.content import process_values
from vodoo.exceptions import VodooError
from vodoo.transport import (
    JSON2Transport,
    LegacyTransport,
    OdooTransport,
)


class OdooClient:
    """Odoo client for external API access.

    Wraps an OdooTransport to provide a convenient interface for Odoo operations.
    Supports both legacy JSON-RPC (Odoo 14-18) and JSON-2 API (Odoo 19+).
    """

    def __init__(
        self,
        config: OdooConfig,
        *,
        transport: OdooTransport | None = None,
        auto_detect: bool = True,
    ) -> None:
        """Initialize Odoo client.

        Args:
            config: Odoo configuration
            transport: Explicit transport instance (skips auto-detection)
            auto_detect: If True and no transport given, probe JSON-2 first then
                         fall back to legacy. If False, use legacy directly.
        """
        self.config = config
        self.url = config.url.rstrip("/")
        self.db = config.database
        self.username = config.username
        self.password = config.password
        self._retry = config.retry_config

        if transport is not None:
            self._transport = transport
        elif auto_detect:
            self._transport = self._detect_transport()
        else:
            self._transport = LegacyTransport(
                url=self.url,
                database=self.db,
                username=self.username,
                password=self.password,
                retry=self._retry,
            )

        # Domain namespaces
        self.helpdesk = _make_helpdesk(self)
        self.crm = _make_crm(self)
        self.tasks = _make_tasks(self)
        self.projects = _make_projects(self)
        self.knowledge = _make_knowledge(self)
        self.timer = _make_timer(self)
        self.security = _make_security(self)
        self.generic = _make_generic(self)

    @property
    def transport(self) -> OdooTransport:
        """The underlying transport."""
        return self._transport

    @property
    def is_json2(self) -> bool:
        """Whether the client is using the JSON-2 API (Odoo 19+)."""
        return isinstance(self._transport, JSON2Transport)

    def _detect_transport(self) -> OdooTransport:
        """Auto-detect Odoo version and return appropriate transport."""
        json2 = JSON2Transport(
            url=self.url,
            database=self.db,
            username=self.username,
            password=self.password,
            retry=self._retry,
        )
        try:
            json2.authenticate()
            return json2
        except VodooError:
            json2.close()
            return LegacyTransport(
                url=self.url,
                database=self.db,
                username=self.username,
                password=self.password,
                retry=self._retry,
            )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._transport.close()

    def __enter__(self) -> "OdooClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @property
    def uid(self) -> int:
        """Get authenticated user ID."""
        return self._transport.uid

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
        return self._transport.execute_kw(model, method, list(args), kwargs or None)

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
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Method result
        """
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
        """Search for records."""
        return self._transport.search(model, domain, limit, offset, order)

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records by IDs."""
        return self._transport.read(model, ids, fields)

    def search_read(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search and read records in one call."""
        return self._transport.search_read(model, domain, fields, limit, offset, order)

    def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        """Create a new record."""
        return self._transport.create(model, process_values(values), context)

    def write(
        self,
        model: str,
        ids: list[int],
        values: dict[str, Any],
    ) -> bool:
        """Update records."""
        return self._transport.write(model, ids, process_values(values))

    def unlink(
        self,
        model: str,
        ids: list[int],
    ) -> bool:
        """Delete records."""
        return self._transport.unlink(model, ids)

    def name_search(
        self,
        model: str,
        name: str,
        domain: list[Any] | None = None,
        limit: int = 7,
    ) -> list[tuple[int, str]]:
        """Autocomplete search returning (id, display_name) pairs."""
        return self._transport.name_search(model, name, domain, limit)


# ---------------------------------------------------------------------------
# Lazy namespace factories (avoid circular imports)
# ---------------------------------------------------------------------------


def _make_helpdesk(client: OdooClient) -> Any:
    from vodoo.helpdesk import HelpdeskNamespace

    return HelpdeskNamespace(client)


def _make_crm(client: OdooClient) -> Any:
    from vodoo.crm import CRMNamespace

    return CRMNamespace(client)


def _make_tasks(client: OdooClient) -> Any:
    from vodoo.project import TaskNamespace

    return TaskNamespace(client)


def _make_projects(client: OdooClient) -> Any:
    from vodoo.project_project import ProjectNamespace

    return ProjectNamespace(client)


def _make_knowledge(client: OdooClient) -> Any:
    from vodoo.knowledge import KnowledgeNamespace

    return KnowledgeNamespace(client)


def _make_timer(client: OdooClient) -> Any:
    from vodoo.timer import TimerNamespace

    return TimerNamespace(client)


def _make_security(client: OdooClient) -> Any:
    from vodoo.security import SecurityNamespace

    return SecurityNamespace(client)


def _make_generic(client: OdooClient) -> Any:
    from vodoo.generic import GenericNamespace

    return GenericNamespace(client)
