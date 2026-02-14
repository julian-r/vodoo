"""Async project (project.project) operations for Vodoo."""

from typing import Any

from vodoo.aio.base import (
    add_comment as base_add_comment,
)
from vodoo.aio.base import (
    add_note as base_add_note,
)
from vodoo.aio.base import (
    create_attachment as base_create_attachment,
)
from vodoo.aio.base import (
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
from vodoo.aio.client import AsyncOdooClient
from vodoo.project_project import (
    DEFAULT_LIST_FIELDS,
    MODEL,
    STAGE_FIELDS,
)
from vodoo.project_project import (
    display_stages as display_stages,
)


async def list_projects(
    client: AsyncOdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List projects."""
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)
    return await list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_projects(projects: list[dict[str, Any]]) -> None:
    """Display projects in a rich table."""
    display_records(projects, title="Projects")


async def get_project(
    client: AsyncOdooClient,
    project_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed project information."""
    return await get_record(client, MODEL, project_id, fields=fields)


async def list_project_fields(client: AsyncOdooClient) -> dict[str, Any]:
    """Get all available fields for projects."""
    return await list_fields(client, MODEL)


async def set_project_fields(
    client: AsyncOdooClient,
    project_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a project."""
    return await set_record_fields(client, MODEL, project_id, values)


def display_project_detail(project: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed project information."""
    display_record_detail(project, MODEL, show_html=show_html, record_type="Project")


async def add_comment(
    client: AsyncOdooClient,
    project_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a project (visible to followers)."""
    return await base_add_comment(
        client, MODEL, project_id, message, user_id=user_id, markdown=markdown
    )


async def add_note(
    client: AsyncOdooClient,
    project_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a project."""
    return await base_add_note(
        client, MODEL, project_id, message, user_id=user_id, markdown=markdown
    )


async def list_project_messages(
    client: AsyncOdooClient,
    project_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a project."""
    return await list_messages(client, MODEL, project_id, limit=limit)


async def list_project_attachments(
    client: AsyncOdooClient,
    project_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a project."""
    return await list_attachments(client, MODEL, project_id)


async def create_project_attachment(
    client: AsyncOdooClient,
    project_id: int,
    file_path: Any,
    name: str | None = None,
) -> int:
    """Create an attachment for a project."""
    return await base_create_attachment(client, MODEL, project_id, file_path, name=name)


def get_project_url(client: AsyncOdooClient, project_id: int) -> str:
    """Get the web URL for a project."""
    return get_record_url(client, MODEL, project_id)


async def list_stages(
    client: AsyncOdooClient,
    project_id: int | None = None,
) -> list[dict[str, Any]]:
    """List task stages, optionally filtered by project."""
    domain: list[Any] = []
    if project_id is not None:
        domain.append(("project_ids", "in", [project_id]))

    return await client.search_read(
        "project.task.type",
        domain=domain,
        fields=STAGE_FIELDS,
        order="sequence",
    )


# display_stages is imported from vodoo.project_project (pure function, no I/O)
