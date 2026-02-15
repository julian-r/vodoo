"""Async helpdesk domain namespace for Vodoo."""

from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.helpdesk import (
    HelpdeskNamespace,
    _build_ticket_values,
    display_ticket_detail,
    display_tickets,
)


class AsyncHelpdeskNamespace(AsyncDomainNamespace):
    """Async namespace for ``helpdesk.ticket`` operations."""

    _model = HelpdeskNamespace._model
    _tag_model = HelpdeskNamespace._tag_model
    _default_fields = HelpdeskNamespace._default_fields
    _record_type = HelpdeskNamespace._record_type

    async def create(
        self,
        name: str,
        *,
        description: str | None = None,
        partner_id: int | None = None,
        tag_ids: list[int] | None = None,
        team_id: int | None = None,
        **extra_fields: Any,
    ) -> int:
        """Create a helpdesk ticket.

        Args:
            name: Ticket title/name.
            description: Ticket description (HTML or plain text).
            partner_id: Customer partner ID.
            tag_ids: List of tag IDs to apply.
            team_id: Helpdesk team ID.
            **extra_fields: Additional fields to set on the ticket.

        Returns:
            ID of created ticket.
        """
        values = _build_ticket_values(
            name,
            description=description,
            partner_id=partner_id,
            tag_ids=tag_ids,
            team_id=team_id,
            **extra_fields,
        )
        return await self._client.create(self._model, values)


__all__ = [
    "AsyncHelpdeskNamespace",
    "display_ticket_detail",
    "display_tickets",
]
