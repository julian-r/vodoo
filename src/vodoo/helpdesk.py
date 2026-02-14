"""Helpdesk operations for Vodoo.

Each domain module (helpdesk, crm, project, etc.) deliberately uses explicit
one-liner delegates to :mod:`vodoo.base` rather than a generic registry or
class-based dispatch.  This is verbose (~15 functions per module, duplicated
for async) but keeps every function independently discoverable in IDE
autocomplete, grep, and generated docs, and makes stack traces trivial to
follow.  The maintenance cost of these thin wrappers is near-zero.
"""

from pathlib import Path
from typing import Any

from vodoo.base import (
    add_comment as base_add_comment,
)
from vodoo.base import (
    add_note as base_add_note,
)
from vodoo.base import (
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
from vodoo.base import (
    create_attachment as base_create_attachment,
)
from vodoo.base import (
    display_tags as base_display_tags,
)
from vodoo.base import (
    list_attachments as base_list_attachments,
)
from vodoo.base import (
    list_messages as base_list_messages,
)
from vodoo.base import (
    list_tags as base_list_tags,
)
from vodoo.client import OdooClient

# Model name constant
MODEL = "helpdesk.ticket"
TAG_MODEL = "helpdesk.tag"

# Default fields for list operations
DEFAULT_LIST_FIELDS = [
    "id",
    "name",
    "partner_id",
    "stage_id",
    "user_id",
    "priority",
    "tag_ids",
    "create_date",
]


def list_tickets(
    client: OdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List helpdesk tickets.

    Args:
        client: Odoo client
        domain: Search domain filters
        limit: Maximum number of tickets
        fields: List of fields to fetch (None = default fields)

    Returns:
        List of ticket dictionaries

    """
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)

    return list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_tickets(tickets: list[dict[str, Any]]) -> None:
    """Display tickets in a rich table.

    Args:
        tickets: List of ticket dictionaries

    """
    display_records(tickets, title="Helpdesk Tickets")


def get_ticket(
    client: OdooClient,
    ticket_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed ticket information.

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        fields: List of field names to read (None = all fields)

    Returns:
        Ticket dictionary

    Raises:
        ValueError: If ticket not found

    """
    return get_record(client, MODEL, ticket_id, fields=fields)


def list_ticket_fields(client: OdooClient) -> dict[str, Any]:
    """Get all available fields for helpdesk tickets.

    Args:
        client: Odoo client

    Returns:
        Dictionary of field definitions with field names as keys

    """
    return list_fields(client, MODEL)


def set_ticket_fields(
    client: OdooClient,
    ticket_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a ticket.

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        values: Dictionary of field names and values to update

    Returns:
        True if successful

    Examples:
        >>> set_ticket_fields(client, 42, {"name": "New title", "priority": "2"})
        >>> set_ticket_fields(client, 42, {"user_id": 5, "stage_id": 3})

    """
    return set_record_fields(client, MODEL, ticket_id, values)


def display_ticket_detail(ticket: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed ticket information.

    Args:
        ticket: Ticket dictionary
        show_html: If True, show raw HTML description, else convert to markdown

    """
    display_record_detail(ticket, show_html=show_html, record_type="Ticket")


def add_comment(
    client: OdooClient,
    ticket_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a ticket (visible to customers).

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        message: Comment message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
        markdown: If True, convert markdown to HTML

    Returns:
        True if successful

    """
    return base_add_comment(client, MODEL, ticket_id, message, user_id=user_id, markdown=markdown)


def add_note(
    client: OdooClient,
    ticket_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a ticket (not visible to customers).

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        message: Note message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
        markdown: If True, convert markdown to HTML

    Returns:
        True if successful

    """
    return base_add_note(client, MODEL, ticket_id, message, user_id=user_id, markdown=markdown)


def list_tags(client: OdooClient) -> list[dict[str, Any]]:
    """List available helpdesk tags.

    Args:
        client: Odoo client

    Returns:
        List of tag dictionaries

    """
    return base_list_tags(client, TAG_MODEL)


def display_tags(tags: list[dict[str, Any]]) -> None:
    """Display tags in a rich table.

    Args:
        tags: List of tag dictionaries

    """
    base_display_tags(tags, title="Helpdesk Tags")


def add_tag_to_ticket(
    client: OdooClient,
    ticket_id: int,
    tag_id: int,
) -> bool:
    """Add a tag to a ticket.

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        tag_id: Tag ID

    Returns:
        True if successful

    """
    return add_tag_to_record(client, MODEL, ticket_id, tag_id)


def list_messages(
    client: OdooClient,
    ticket_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a ticket.

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        limit: Maximum number of messages (None = all)

    Returns:
        List of message dictionaries

    """
    return base_list_messages(client, MODEL, ticket_id, limit=limit)


def list_attachments(
    client: OdooClient,
    ticket_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a ticket.

    Args:
        client: Odoo client
        ticket_id: Ticket ID

    Returns:
        List of attachment dictionaries

    """
    return base_list_attachments(client, MODEL, ticket_id)


def download_ticket_attachments(
    client: OdooClient,
    ticket_id: int,
    output_dir: Path | None = None,
    extension: str | None = None,
) -> list[Path]:
    """Download all attachments from a ticket.

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        output_dir: Output directory (defaults to current directory)
        extension: File extension filter (e.g., 'pdf', 'jpg')

    Returns:
        List of paths to downloaded files

    """
    return download_record_attachments(client, MODEL, ticket_id, output_dir, extension=extension)


def create_attachment(
    client: OdooClient,
    ticket_id: int,
    file_path: Path | str | None = None,
    *,
    data: bytes | None = None,
    name: str | None = None,
) -> int:
    """Create an attachment for a ticket.
    Args:
        client: Odoo client
        ticket_id: Ticket ID
        file_path: Path to file to attach (mutually exclusive with data)
        data: Raw bytes to attach (mutually exclusive with file_path)
        name: Attachment name (defaults to filename; required when using data)
        ID of created attachment
    Raises:
        ValueError: If arguments are invalid
        FileNotFoundError: If file path is invalid
    Examples:
        >>> create_attachment(client, 42, "screenshot.png")
        >>> create_attachment(client, 42, "/path/to/file.pdf", name="Report.pdf")
        >>> create_attachment(client, 42, data=b"content", name="doc.txt")
    """
    return base_create_attachment(client, MODEL, ticket_id, file_path, data=data, name=name)


def get_ticket_url(client: OdooClient, ticket_id: int) -> str:
    """Get the web URL for a ticket.

    Args:
        client: Odoo client
        ticket_id: Ticket ID

    Returns:
        URL to view the ticket in Odoo web interface

    Examples:
        >>> get_ticket_url(client, 42)
        'https://odoo.example.com/web#id=42&model=helpdesk.ticket&view_type=form'

    """
    return get_record_url(client, MODEL, ticket_id)
