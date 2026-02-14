"""Async base operations for Odoo models.

Provides async versions of I/O functions from :mod:`vodoo.base`.
Pure display/formatting functions are re-exported unchanged.
"""

import base64
from pathlib import Path
from typing import Any

from vodoo.aio.auth import message_post_sudo
from vodoo.aio.client import AsyncOdooClient
from vodoo.base import (
    _convert_to_html,
    _format_field_value,
    _get_console,
    _html_to_markdown,
    _is_simple_output,
    configure_output,
    display_attachments,
    display_messages,
    display_record_detail,
    display_records,
    display_tags,
    get_record_url,
)
from vodoo.exceptions import FieldParsingError, RecordNotFoundError

# Re-export pure functions so async domain modules can import everything from here
__all__ = [
    "_convert_to_html",
    "_format_field_value",
    "_get_console",
    "_html_to_markdown",
    "_is_simple_output",
    "add_comment",
    "add_note",
    "add_tag_to_record",
    "configure_output",
    "create_attachment",
    "display_attachments",
    "display_messages",
    "display_record_detail",
    "display_records",
    "display_tags",
    "download_attachment",
    "download_record_attachments",
    "get_record",
    "get_record_url",
    "list_attachments",
    "list_fields",
    "list_messages",
    "list_records",
    "list_tags",
    "parse_field_assignment",
    "set_record_fields",
]


async def list_records(
    client: AsyncOdooClient,
    model: str,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
    order: str = "create_date desc",
) -> list[dict[str, Any]]:
    """List records from a model.

    Args:
        client: Async Odoo client
        model: Model name
        domain: Search domain filters
        limit: Maximum number of records
        fields: List of fields to fetch
        order: Sort order

    Returns:
        List of record dictionaries
    """
    return await client.search_read(
        model,
        domain=domain,
        fields=fields,
        limit=limit,
        order=order,
    )


async def get_record(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed record information.

    Args:
        client: Async Odoo client
        model: Model name
        record_id: Record ID
        fields: List of field names to read

    Returns:
        Record dictionary

    Raises:
        RecordNotFoundError: If record not found
    """
    records = await client.read(model, [record_id], fields=fields)
    if not records:
        raise RecordNotFoundError(model, record_id)
    return records[0]


async def list_fields(client: AsyncOdooClient, model: str) -> dict[str, Any]:
    """Get all available fields for a model."""
    result: dict[str, Any] = await client.execute(model, "fields_get")
    return result


async def set_record_fields(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a record."""
    return await client.write(model, [record_id], values)


async def add_comment(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a record (visible to customers)."""
    body = _convert_to_html(message, markdown)
    return await message_post_sudo(
        client,
        model,
        record_id,
        body,
        user_id=user_id,
        is_note=False,
    )


async def add_note(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a record (not visible to customers)."""
    body = _convert_to_html(message, markdown)
    return await message_post_sudo(
        client,
        model,
        record_id,
        body,
        user_id=user_id,
        is_note=True,
    )


async def list_tags(client: AsyncOdooClient, model: str) -> list[dict[str, Any]]:
    """List available tags for a model."""
    fields = ["id", "name", "color"]
    return await client.search_read(model, fields=fields, order="name")


async def add_tag_to_record(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    tag_id: int,
) -> bool:
    """Add a tag to a record."""
    record = await get_record(client, model, record_id)
    current_tags = record.get("tag_ids", [])
    if tag_id not in current_tags:
        current_tags.append(tag_id)
        return await client.write(
            model,
            [record_id],
            {"tag_ids": [(6, 0, current_tags)]},
        )
    return True


async def list_messages(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a record."""
    domain: list[Any] = [
        ("model", "=", model),
        ("res_id", "=", record_id),
    ]
    fields = [
        "id",
        "date",
        "author_id",
        "body",
        "subject",
        "message_type",
        "subtype_id",
        "email_from",
    ]
    return await client.search_read(
        "mail.message",
        domain=domain,
        fields=fields,
        order="date desc",
        limit=limit,
    )


async def list_attachments(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a record."""
    domain: list[Any] = [
        ("res_model", "=", model),
        ("res_id", "=", record_id),
    ]
    fields = ["id", "name", "file_size", "mimetype", "create_date"]
    return await client.search_read("ir.attachment", domain=domain, fields=fields)


async def download_attachment(
    client: AsyncOdooClient,
    attachment_id: int,
    output_path: Path | None = None,
) -> Path:
    """Download an attachment.

    Args:
        client: Async Odoo client
        attachment_id: Attachment ID
        output_path: Output file path

    Returns:
        Path to downloaded file

    Raises:
        RecordNotFoundError: If attachment not found
    """
    attachments = await client.read("ir.attachment", [attachment_id], ["name", "datas"])
    if not attachments:
        raise RecordNotFoundError("ir.attachment", attachment_id)

    attachment = attachments[0]
    filename = attachment.get("name", f"attachment_{attachment_id}")

    if output_path is None:
        output_path = Path.cwd() / filename
    elif output_path.is_dir():
        output_path = output_path / filename

    if attachment.get("datas"):
        data = base64.b64decode(attachment["datas"])
        output_path.write_bytes(data)
    else:
        raise RecordNotFoundError("ir.attachment", attachment_id)

    return output_path


async def download_record_attachments(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    output_dir: Path | None = None,
    extension: str | None = None,
) -> list[Path]:
    """Download all attachments for a record."""
    if output_dir is None:
        output_dir = Path.cwd()
    elif not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    attachments = await list_attachments(client, model, record_id)

    if extension:
        ext = extension.lower().lstrip(".")
        attachments = [
            att for att in attachments if att.get("name", "").lower().endswith(f".{ext}")
        ]

    downloaded_files: list[Path] = []
    console = _get_console()

    for attachment in attachments:
        filename = attachment.get("name", f"attachment_{attachment['id']}")
        try:
            att_data = await client.read("ir.attachment", [attachment["id"]], ["name", "datas"])
            if not att_data:
                continue

            att = att_data[0]
            filename = att.get("name", f"attachment_{attachment['id']}")
            output_path = output_dir / filename

            if att.get("datas"):
                data = base64.b64decode(att["datas"])
                output_path.write_bytes(data)
                downloaded_files.append(output_path)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to download {filename}: {e}[/yellow]")
            continue

    return downloaded_files


async def create_attachment(
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    file_path: Path | str,
    name: str | None = None,
) -> int:
    """Create an attachment for a record.

    Args:
        client: Async Odoo client
        model: Model name
        record_id: Record ID
        file_path: Path to file to attach
        name: Attachment name (defaults to filename)

    Returns:
        ID of created attachment

    Raises:
        FileNotFoundError: If file path is invalid
        ValueError: If path is not a file
    """
    file_path = Path(file_path)

    if not file_path.exists():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    if not file_path.is_file():
        msg = f"Path is not a file: {file_path}"
        raise ValueError(msg)

    file_data = file_path.read_bytes()
    encoded_data = base64.b64encode(file_data).decode("utf-8")
    attachment_name = name or file_path.name

    values = {
        "name": attachment_name,
        "datas": encoded_data,
        "res_model": model,
        "res_id": record_id,
    }

    return await client.create("ir.attachment", values)


async def parse_field_assignment(  # noqa: PLR0912, PLR0915
    client: AsyncOdooClient,
    model: str,
    record_id: int,
    field_assignment: str,
    no_markdown: bool = False,
) -> tuple[str, Any]:
    """Parse a field assignment and return field name and computed value.

    Supports operators: =, +=, -=, *=, /=
    HTML fields automatically get markdown conversion unless no_markdown=True.
    """
    import contextlib
    import json
    import re

    match = re.match(r"^([^=+\-*/]+)([\+\-*/]?=)(.+)$", field_assignment, re.DOTALL)
    if not match:
        msg = f"Invalid format '{field_assignment}'. Use field=value or field+=value"
        raise FieldParsingError(msg)

    field = match.group(1).strip()
    operator = match.group(2).strip()
    value = match.group(3).strip()

    parsed_value: Any = value

    if value.startswith("json:"):
        try:
            parsed_value = json.loads(value[5:])
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON for field '{field}': {e}"
            raise FieldParsingError(msg) from e
    elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        parsed_value = int(value)
    elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
        with contextlib.suppress(ValueError):
            parsed_value = float(value)
    elif value.lower() in ("true", "false"):
        parsed_value = value.lower() == "true"
    elif (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        parsed_value = value[1:-1]

    if isinstance(parsed_value, str) and not no_markdown:
        fields_info = await list_fields(client, model)
        if field in fields_info and fields_info[field].get("type") == "html":
            parsed_value = _convert_to_html(parsed_value, use_markdown=True)

    if operator in ("+=", "-=", "*=", "/="):
        record = await get_record(client, model, record_id, fields=[field])
        current_value = record.get(field)

        if current_value is None:
            msg = f"Field '{field}' not found or is None"
            raise FieldParsingError(msg)

        if not isinstance(current_value, (int, float)):
            msg = f"Field '{field}' has non-numeric value: {current_value}"
            raise FieldParsingError(msg)

        if not isinstance(parsed_value, (int, float)):
            msg = f"Operator '{operator}' requires numeric value, got: {value}"
            raise FieldParsingError(msg)

        if operator == "+=":
            parsed_value = current_value + parsed_value
        elif operator == "-=":
            parsed_value = current_value - parsed_value
        elif operator == "*=":
            parsed_value = current_value * parsed_value
        elif operator == "/=":
            if parsed_value == 0:
                msg = "Division by zero"
                raise FieldParsingError(msg)
            parsed_value = current_value / parsed_value

    return field, parsed_value
