"""Project (project.project) operations for Odoo Ninja."""

from typing import Any

from odoo_ninja.base import (
    add_comment as base_add_comment,
)
from odoo_ninja.base import (
    add_note as base_add_note,
)
from odoo_ninja.base import (
    create_attachment as base_create_attachment,
)
from odoo_ninja.base import (
    display_record_detail,
    display_records,
    get_record,
    get_record_url,
    list_attachments,
    list_fields,
    list_messages,
    list_records,
    set_record_fields,
)
from odoo_ninja.client import OdooClient

# Model name constant
MODEL = "project.project"


def list_projects(
    client: OdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List projects.

    Args:
        client: Odoo client
        domain: Search domain filters
        limit: Maximum number of projects
        fields: List of fields to fetch (None = default fields)

    Returns:
        List of project dictionaries

    """
    if fields is None:
        fields = [
            "id",
            "name",
            "user_id",
            "partner_id",
            "date_start",
            "date",
            "task_count",
            "color",
        ]

    return list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_projects(projects: list[dict[str, Any]]) -> None:
    """Display projects in a rich table.

    Args:
        projects: List of project dictionaries

    """
    display_records(projects, title="Projects")


def get_project(
    client: OdooClient,
    project_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed project information.

    Args:
        client: Odoo client
        project_id: Project ID
        fields: List of field names to read (None = all fields)

    Returns:
        Project dictionary

    Raises:
        ValueError: If project not found

    """
    return get_record(client, MODEL, project_id, fields=fields)


def list_project_fields(client: OdooClient) -> dict[str, Any]:
    """Get all available fields for projects.

    Args:
        client: Odoo client

    Returns:
        Dictionary of field definitions with field names as keys

    """
    return list_fields(client, MODEL)


def set_project_fields(
    client: OdooClient,
    project_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a project.

    Args:
        client: Odoo client
        project_id: Project ID
        values: Dictionary of field names and values to update

    Returns:
        True if successful

    Examples:
        >>> set_project_fields(client, 42, {"name": "New Project Name"})
        >>> set_project_fields(client, 42, {"user_id": 5})

    """
    return set_record_fields(client, MODEL, project_id, values)


def display_project_detail(project: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed project information.

    Args:
        project: Project dictionary
        show_html: If True, show raw HTML description, else convert to markdown

    """
    display_record_detail(project, MODEL, show_html=show_html, record_type="Project")


def add_comment(
    client: OdooClient,
    project_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = False,
) -> bool:
    """Add a comment to a project (visible to followers).

    Args:
        client: Odoo client
        project_id: Project ID
        message: Comment message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
        markdown: If True, convert markdown to HTML

    Returns:
        True if successful

    """
    return base_add_comment(client, MODEL, project_id, message, user_id=user_id, markdown=markdown)


def add_note(
    client: OdooClient,
    project_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = False,
) -> bool:
    """Add an internal note to a project.

    Args:
        client: Odoo client
        project_id: Project ID
        message: Note message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
        markdown: If True, convert markdown to HTML

    Returns:
        True if successful

    """
    return base_add_note(client, MODEL, project_id, message, user_id=user_id, markdown=markdown)


def list_project_messages(
    client: OdooClient,
    project_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a project.

    Args:
        client: Odoo client
        project_id: Project ID
        limit: Maximum number of messages (None = all)

    Returns:
        List of message dictionaries

    """
    return list_messages(client, MODEL, project_id, limit=limit)


def list_project_attachments(
    client: OdooClient,
    project_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a project.

    Args:
        client: Odoo client
        project_id: Project ID

    Returns:
        List of attachment dictionaries

    """
    return list_attachments(client, MODEL, project_id)


def create_project_attachment(
    client: OdooClient,
    project_id: int,
    file_path: Any,
    name: str | None = None,
) -> int:
    """Create an attachment for a project.

    Args:
        client: Odoo client
        project_id: Project ID
        file_path: Path to file to attach
        name: Attachment name (defaults to filename)

    Returns:
        ID of created attachment

    """
    return base_create_attachment(client, MODEL, project_id, file_path, name=name)


def get_project_url(client: OdooClient, project_id: int) -> str:
    """Get the web URL for a project.

    Args:
        client: Odoo client
        project_id: Project ID

    Returns:
        URL to view the project in Odoo web interface

    """
    return get_record_url(client, MODEL, project_id)
