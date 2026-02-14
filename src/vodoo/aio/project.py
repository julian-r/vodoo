"""Async project task operations for Vodoo."""

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
    display_tags,
    download_record_attachments,
    get_record,
    get_record_url,
    list_attachments,
    list_fields,
    list_messages,
    list_records,
    set_record_fields,
)
from vodoo.aio.base import (
    create_attachment as base_create_attachment,
)
from vodoo.aio.base import (
    list_tags as base_list_tags,
)
from vodoo.aio.client import AsyncOdooClient
from vodoo.project import DEFAULT_LIST_FIELDS, MODEL, TAG_MODEL, _build_task_values


async def create_task(
    client: AsyncOdooClient,
    name: str,
    project_id: int,
    description: str | None = None,
    user_ids: list[int] | None = None,
    tag_ids: list[int] | None = None,
    parent_id: int | None = None,
    **kwargs: Any,
) -> int:
    """Create a new project task."""
    values, context = _build_task_values(
        name, project_id, description, user_ids, tag_ids, parent_id, **kwargs
    )
    return await client.create(MODEL, values, context=context)


async def list_tasks(
    client: AsyncOdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List project tasks."""
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)
    return await list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_tasks(tasks: list[dict[str, Any]]) -> None:
    """Display tasks in a rich table."""
    display_records(tasks, title="Project Tasks")


async def get_task(
    client: AsyncOdooClient,
    task_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed task information."""
    return await get_record(client, MODEL, task_id, fields=fields)


async def list_task_fields(client: AsyncOdooClient) -> dict[str, Any]:
    """Get all available fields for project tasks."""
    return await list_fields(client, MODEL)


async def set_task_fields(
    client: AsyncOdooClient,
    task_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a task."""
    return await set_record_fields(client, MODEL, task_id, values)


def display_task_detail(task: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed task information."""
    display_record_detail(task, show_html=show_html, record_type="Task")


async def add_comment(
    client: AsyncOdooClient,
    task_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a task (visible to followers)."""
    return await base_add_comment(
        client, MODEL, task_id, message, user_id=user_id, markdown=markdown
    )


async def add_note(
    client: AsyncOdooClient,
    task_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a task."""
    return await base_add_note(client, MODEL, task_id, message, user_id=user_id, markdown=markdown)


async def list_task_tags(client: AsyncOdooClient) -> list[dict[str, Any]]:
    """List available project tags."""
    return await base_list_tags(client, TAG_MODEL)


def display_task_tags(tags: list[dict[str, Any]]) -> None:
    """Display project tags in a rich table."""
    display_tags(tags, title="Project Tags")


async def add_tag_to_task(
    client: AsyncOdooClient,
    task_id: int,
    tag_id: int,
) -> bool:
    """Add a tag to a task."""
    return await add_tag_to_record(client, MODEL, task_id, tag_id)


async def create_tag(
    client: AsyncOdooClient,
    name: str,
    color: int | None = None,
) -> int:
    """Create a new project tag."""
    values: dict[str, Any] = {"name": name}
    if color is not None:
        values["color"] = color
    return await client.create(TAG_MODEL, values)


async def delete_tag(
    client: AsyncOdooClient,
    tag_id: int,
) -> bool:
    """Delete a project tag."""
    return await client.unlink(TAG_MODEL, [tag_id])


async def list_task_messages(
    client: AsyncOdooClient,
    task_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a task."""
    return await list_messages(client, MODEL, task_id, limit=limit)


async def list_task_attachments(
    client: AsyncOdooClient,
    task_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a task."""
    return await list_attachments(client, MODEL, task_id)


async def download_task_attachments(
    client: AsyncOdooClient,
    task_id: int,
    output_dir: Path | None = None,
    extension: str | None = None,
) -> list[Path]:
    """Download all attachments from a task."""
    return await download_record_attachments(
        client, MODEL, task_id, output_dir, extension=extension
    )


async def create_task_attachment(
    client: AsyncOdooClient,
    task_id: int,
    file_path: Path | str,
    name: str | None = None,
) -> int:
    """Create an attachment for a task."""
    return await base_create_attachment(client, MODEL, task_id, file_path, name=name)


def get_task_url(client: AsyncOdooClient, task_id: int) -> str:
    """Get the web URL for a task."""
    return get_record_url(client, MODEL, task_id)
