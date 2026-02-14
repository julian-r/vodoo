"""Async helpdesk operations for Vodoo."""

from typing import Any

from vodoo.aio.base import (
    add_comment as base_add_comment,
)
from vodoo.aio.base import (
    add_note as base_add_note,
)
from vodoo.aio.base import (
    add_tag_to_record,
    display_record_detail,
    display_records,
    download_record_attachments,
    get_record,
    get_record_url,
    list_fields,
    list_records,
    set_record_fields,
)
from vodoo.aio.base import (
    create_attachment as base_create_attachment,
)
from vodoo.aio.base import (
    display_tags as base_display_tags,
)
from vodoo.aio.base import (
    list_attachments as base_list_attachments,
)
from vodoo.aio.base import (
    list_messages as base_list_messages,
)
from vodoo.aio.base import (
    list_tags as base_list_tags,
)
from vodoo.aio.client import AsyncOdooClient
from vodoo.helpdesk import DEFAULT_LIST_FIELDS, MODEL, TAG_MODEL


async def list_tickets(
    client: AsyncOdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List helpdesk tickets."""
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)
    return await list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_tickets(tickets: list[dict[str, Any]]) -> None:
    """Display tickets in a rich table."""
    display_records(tickets, title="Helpdesk Tickets")


async def get_ticket(
    client: AsyncOdooClient,
    ticket_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed ticket information."""
    return await get_record(client, MODEL, ticket_id, fields=fields)


async def list_ticket_fields(client: AsyncOdooClient) -> dict[str, Any]:
    """Get all available fields for helpdesk tickets."""
    return await list_fields(client, MODEL)


async def set_ticket_fields(
    client: AsyncOdooClient,
    ticket_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a ticket."""
    return await set_record_fields(client, MODEL, ticket_id, values)


def display_ticket_detail(ticket: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed ticket information."""
    display_record_detail(ticket, show_html=show_html, record_type="Ticket")


async def add_comment(
    client: AsyncOdooClient,
    ticket_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a ticket (visible to customers)."""
    return await base_add_comment(
        client, MODEL, ticket_id, message, user_id=user_id, markdown=markdown
    )


async def add_note(
    client: AsyncOdooClient,
    ticket_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a ticket (not visible to customers)."""
    return await base_add_note(
        client, MODEL, ticket_id, message, user_id=user_id, markdown=markdown
    )


async def list_tags(client: AsyncOdooClient) -> list[dict[str, Any]]:
    """List available helpdesk tags."""
    return await base_list_tags(client, TAG_MODEL)


def display_tags(tags: list[dict[str, Any]]) -> None:
    """Display tags in a rich table."""
    base_display_tags(tags, title="Helpdesk Tags")


async def add_tag_to_ticket(
    client: AsyncOdooClient,
    ticket_id: int,
    tag_id: int,
) -> bool:
    """Add a tag to a ticket."""
    return await add_tag_to_record(client, MODEL, ticket_id, tag_id)


async def list_messages(
    client: AsyncOdooClient,
    ticket_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a ticket."""
    return await base_list_messages(client, MODEL, ticket_id, limit=limit)


async def list_attachments(
    client: AsyncOdooClient,
    ticket_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a ticket."""
    return await base_list_attachments(client, MODEL, ticket_id)


async def download_ticket_attachments(
    client: AsyncOdooClient,
    ticket_id: int,
    output_dir: Any = None,
    extension: str | None = None,
) -> list[Any]:
    """Download all attachments from a ticket."""
    return await download_record_attachments(
        client, MODEL, ticket_id, output_dir, extension=extension
    )


async def create_attachment(
    client: AsyncOdooClient,
    ticket_id: int,
    file_path: Any,
    name: str | None = None,
) -> int:
    """Create an attachment for a ticket."""
    return await base_create_attachment(client, MODEL, ticket_id, file_path, name=name)


def get_ticket_url(client: AsyncOdooClient, ticket_id: int) -> str:
    """Get the web URL for a ticket."""
    return get_record_url(client, MODEL, ticket_id)
