"""Helpdesk domain namespace for Vodoo."""

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace


class _HelpdeskAttrs:
    """Shared domain attributes for helpdesk namespaces."""

    _model = "helpdesk.ticket"
    _tag_model: str | None = "helpdesk.tag"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "partner_id",
        "stage_id",
        "user_id",
        "priority",
        "tag_ids",
        "create_date",
    ]
    _record_type = "Ticket"


class HelpdeskNamespace(_HelpdeskAttrs, DomainNamespace):
    """Namespace for ``helpdesk.ticket`` operations."""

    def create(
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
        return self._client.create(self._model, values)


# ---------------------------------------------------------------------------
# Module-level helpers (pure data transforms)
# ---------------------------------------------------------------------------


def _build_ticket_values(
    name: str,
    *,
    description: str | None = None,
    partner_id: int | None = None,
    tag_ids: list[int] | None = None,
    team_id: int | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    """Build the values dict for helpdesk.ticket creation."""
    values: dict[str, Any] = {"name": name, **extra_fields}
    if description is not None:
        values["description"] = description
    if partner_id is not None:
        values["partner_id"] = partner_id
    if tag_ids is not None:
        values["tag_ids"] = [(6, 0, tag_ids)]
    if team_id is not None:
        values["team_id"] = team_id
    return values


# ---------------------------------------------------------------------------
# Display functions (no client needed)
# ---------------------------------------------------------------------------
