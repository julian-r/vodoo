"""Async CRM lead/opportunity operations for Vodoo."""

from pathlib import Path
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
from vodoo.crm import DEFAULT_LIST_FIELDS, MODEL, TAG_MODEL


async def list_leads(
    client: AsyncOdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List CRM leads/opportunities."""
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)
    return await list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_leads(leads: list[dict[str, Any]]) -> None:
    """Display leads in a rich table."""
    display_records(leads, title="CRM Leads/Opportunities")


async def get_lead(
    client: AsyncOdooClient,
    lead_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed lead information."""
    return await get_record(client, MODEL, lead_id, fields=fields)


async def list_lead_fields(client: AsyncOdooClient) -> dict[str, Any]:
    """Get all available fields for CRM leads."""
    return await list_fields(client, MODEL)


async def set_lead_fields(
    client: AsyncOdooClient,
    lead_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a lead."""
    return await set_record_fields(client, MODEL, lead_id, values)


def display_lead_detail(lead: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed lead information."""
    display_record_detail(lead, show_html=show_html, record_type="Lead")


async def add_comment(
    client: AsyncOdooClient,
    lead_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a lead (visible to followers)."""
    return await base_add_comment(
        client, MODEL, lead_id, message, user_id=user_id, markdown=markdown
    )


async def add_note(
    client: AsyncOdooClient,
    lead_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a lead."""
    return await base_add_note(client, MODEL, lead_id, message, user_id=user_id, markdown=markdown)


async def list_tags(client: AsyncOdooClient) -> list[dict[str, Any]]:
    """List available CRM tags."""
    return await base_list_tags(client, TAG_MODEL)


def display_tags(tags: list[dict[str, Any]]) -> None:
    """Display tags in a rich table."""
    base_display_tags(tags, title="CRM Tags")


async def add_tag_to_lead(
    client: AsyncOdooClient,
    lead_id: int,
    tag_id: int,
) -> bool:
    """Add a tag to a lead."""
    return await add_tag_to_record(client, MODEL, lead_id, tag_id)


async def list_lead_messages(
    client: AsyncOdooClient,
    lead_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a lead."""
    return await base_list_messages(client, MODEL, lead_id, limit=limit)


async def list_lead_attachments(
    client: AsyncOdooClient,
    lead_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a lead."""
    return await base_list_attachments(client, MODEL, lead_id)


async def download_lead_attachments(
    client: AsyncOdooClient,
    lead_id: int,
    output_dir: Path | None = None,
    extension: str | None = None,
) -> list[Path]:
    """Download all attachments from a lead."""
    return await download_record_attachments(
        client, MODEL, lead_id, output_dir, extension=extension
    )


async def create_lead_attachment(
    client: AsyncOdooClient,
    lead_id: int,
    file_path: Path | str,
    name: str | None = None,
) -> int:
    """Create an attachment for a lead."""
    return await base_create_attachment(client, MODEL, lead_id, file_path, name=name)


def get_lead_url(client: AsyncOdooClient, lead_id: int) -> str:
    """Get the web URL for a lead."""
    return get_record_url(client, MODEL, lead_id)
