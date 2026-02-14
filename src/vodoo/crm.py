"""CRM lead/opportunity operations for Vodoo."""

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
MODEL = "crm.lead"
TAG_MODEL = "crm.tag"

# Default fields for list operations
DEFAULT_LIST_FIELDS = [
    "id",
    "name",
    "partner_id",
    "stage_id",
    "user_id",
    "team_id",
    "expected_revenue",
    "probability",
    "type",
    "priority",
    "tag_ids",
    "create_date",
]


def list_leads(
    client: OdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List CRM leads/opportunities.

    Args:
        client: Odoo client
        domain: Search domain filters
        limit: Maximum number of leads
        fields: List of fields to fetch (None = default fields)

    Returns:
        List of lead dictionaries

    """
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)

    return list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_leads(leads: list[dict[str, Any]]) -> None:
    """Display leads in a rich table.

    Args:
        leads: List of lead dictionaries

    """
    display_records(leads, title="CRM Leads/Opportunities")


def get_lead(
    client: OdooClient,
    lead_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed lead information.

    Args:
        client: Odoo client
        lead_id: Lead ID
        fields: List of field names to read (None = all fields)

    Returns:
        Lead dictionary

    Raises:
        ValueError: If lead not found

    """
    return get_record(client, MODEL, lead_id, fields=fields)


def list_lead_fields(client: OdooClient) -> dict[str, Any]:
    """Get all available fields for CRM leads.

    Args:
        client: Odoo client

    Returns:
        Dictionary of field definitions with field names as keys

    """
    return list_fields(client, MODEL)


def set_lead_fields(
    client: OdooClient,
    lead_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a lead.

    Args:
        client: Odoo client
        lead_id: Lead ID
        values: Dictionary of field names and values to update

    Returns:
        True if successful

    Examples:
        >>> set_lead_fields(client, 42, {"name": "New title", "priority": "2"})
        >>> set_lead_fields(client, 42, {"user_id": 5, "stage_id": 3})

    """
    return set_record_fields(client, MODEL, lead_id, values)


def display_lead_detail(lead: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed lead information.

    Args:
        lead: Lead dictionary
        show_html: If True, show raw HTML description, else convert to markdown

    """
    display_record_detail(lead, show_html=show_html, record_type="Lead")


def add_comment(
    client: OdooClient,
    lead_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a lead (visible to followers).

    Args:
        client: Odoo client
        lead_id: Lead ID
        message: Comment message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
        markdown: If True, convert markdown to HTML

    Returns:
        True if successful

    """
    return base_add_comment(client, MODEL, lead_id, message, user_id=user_id, markdown=markdown)


def add_note(
    client: OdooClient,
    lead_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a lead (not visible to followers).

    Args:
        client: Odoo client
        lead_id: Lead ID
        message: Note message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
        markdown: If True, convert markdown to HTML

    Returns:
        True if successful

    """
    return base_add_note(client, MODEL, lead_id, message, user_id=user_id, markdown=markdown)


def list_tags(client: OdooClient) -> list[dict[str, Any]]:
    """List available CRM tags.

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
    base_display_tags(tags, title="CRM Tags")


def add_tag_to_lead(
    client: OdooClient,
    lead_id: int,
    tag_id: int,
) -> bool:
    """Add a tag to a lead.

    Args:
        client: Odoo client
        lead_id: Lead ID
        tag_id: Tag ID

    Returns:
        True if successful

    """
    return add_tag_to_record(client, MODEL, lead_id, tag_id)


def list_lead_messages(
    client: OdooClient,
    lead_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a lead.

    Args:
        client: Odoo client
        lead_id: Lead ID
        limit: Maximum number of messages (None = all)

    Returns:
        List of message dictionaries

    """
    return base_list_messages(client, MODEL, lead_id, limit=limit)


def list_lead_attachments(
    client: OdooClient,
    lead_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a lead.

    Args:
        client: Odoo client
        lead_id: Lead ID

    Returns:
        List of attachment dictionaries

    """
    return base_list_attachments(client, MODEL, lead_id)


def download_lead_attachments(
    client: OdooClient,
    lead_id: int,
    output_dir: Any = None,
    extension: str | None = None,
) -> list[Any]:
    """Download all attachments from a lead.

    Args:
        client: Odoo client
        lead_id: Lead ID
        output_dir: Output directory (defaults to current directory)
        extension: File extension filter (e.g., 'pdf', 'jpg')

    Returns:
        List of paths to downloaded files

    """
    return download_record_attachments(client, MODEL, lead_id, output_dir, extension=extension)


def create_lead_attachment(
    client: OdooClient,
    lead_id: int,
    file_path: Any,
    name: str | None = None,
) -> int:
    """Create an attachment for a lead.

    Args:
        client: Odoo client
        lead_id: Lead ID
        file_path: Path to file to attach
        name: Attachment name (defaults to filename)

    Returns:
        ID of created attachment

    Raises:
        ValueError: If file doesn't exist
        FileNotFoundError: If file path is invalid

    Examples:
        >>> create_lead_attachment(client, 42, "proposal.pdf")
        >>> create_lead_attachment(client, 42, "/path/to/file.pdf", name="Quote.pdf")

    """
    return base_create_attachment(client, MODEL, lead_id, file_path, name=name)


def get_lead_url(client: OdooClient, lead_id: int) -> str:
    """Get the web URL for a lead.

    Args:
        client: Odoo client
        lead_id: Lead ID

    Returns:
        URL to view the lead in Odoo web interface

    Examples:
        >>> get_lead_url(client, 42)
        'https://odoo.example.com/web#id=42&model=crm.lead&view_type=form'

    """
    return get_record_url(client, MODEL, lead_id)
