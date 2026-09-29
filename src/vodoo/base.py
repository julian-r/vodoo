"""Base operations for Odoo models - shared functionality."""

from __future__ import annotations

import base64
import html.parser as _html_parser_mod
from pathlib import Path
from typing import Any

from vodoo.auth import message_post_sudo
from vodoo.client import OdooClient
from vodoo.exceptions import RecordNotFoundError
from vodoo.urls import build_record_url

# Field lists shared with aio.base
_TAG_FIELDS: list[str] = ["id", "name", "color"]
_MESSAGE_FIELDS: list[str] = [
    "id",
    "date",
    "author_id",
    "body",
    "subject",
    "message_type",
    "subtype_id",
    "email_from",
]
_ATTACHMENT_LIST_FIELDS: list[str] = ["id", "name", "file_size", "mimetype", "create_date"]
_ATTACHMENT_READ_FIELDS: list[str] = ["name", "datas"]


def _decode_attachment_data(attachment: dict[str, Any], attachment_id: int) -> bytes:
    """Decode base64 datas from an attachment record, or raise."""
    if not attachment.get("datas"):
        raise RecordNotFoundError("ir.attachment", attachment_id)
    return base64.b64decode(attachment["datas"])


def _decode_attachment_record(att: dict[str, Any], att_id: int) -> tuple[int, str, bytes] | None:
    """Decode a single attachment record into (id, name, bytes), or None if empty."""
    if not att.get("datas"):
        return None
    filename = att.get("name", f"attachment_{att_id}")
    return (att_id, filename, base64.b64decode(att["datas"]))


def mask_binary_fields(
    records: list[dict[str, Any]],
    binary_fields: set[str],
) -> list[dict[str, Any]]:
    """Replace binary field values with a human-readable size summary.

    Binary fields in Odoo are returned as base64-encoded strings which can be
    very large and flood terminal output.  This function replaces them with a
    placeholder like ``<binary 14.2 KB>``.

    Args:
        records: List of record dictionaries (modified in place and returned).
        binary_fields: Set of field names known to be binary.

    Returns:
        The same list with binary values replaced by summary strings.
    """
    for record in records:
        for fname in binary_fields:
            val = record.get(fname)
            if isinstance(val, str) and val:
                raw_bytes = len(val) * 3 // 4  # approximate decoded size
                if raw_bytes < 1024:
                    size_str = f"{raw_bytes} B"
                elif raw_bytes < 1024 * 1024:
                    size_str = f"{raw_bytes / 1024:.1f} KB"
                else:
                    size_str = f"{raw_bytes / (1024 * 1024):.1f} MB"
                record[fname] = f"<binary {size_str}>"
    return records


def detect_binary_fields(
    client: OdooClient,
    model: str,
    field_names: list[str] | None = None,
) -> set[str]:
    """Return the set of field names that are binary type.

    Args:
        client: Odoo client
        model: Model name
        field_names: If given, only check these fields. Otherwise check all.

    Returns:
        Set of field names with type ``binary``.
    """
    fields_info = client.fields_get(model, fields=field_names, attributes=["type"])
    return {name for name, info in fields_info.items() if info.get("type") == "binary"}


def save_binary_field(data: str, output: Path) -> Path:
    """Decode a base64 binary field value and save to a file.

    Args:
        data: Base64-encoded string from Odoo.
        output: Destination file path.

    Returns:
        The resolved output path.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(data))
    return output.resolve()


def list_records(
    client: OdooClient,
    model: str,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
    order: str = "create_date desc",
) -> list[dict[str, Any]]:
    """List records from a model.

    Args:
        client: Odoo client
        model: Model name (e.g., 'helpdesk.ticket', 'project.task')
        domain: Search domain filters
        limit: Maximum number of records
        fields: List of fields to fetch (None = default fields)
        order: Sort order

    Returns:
        List of record dictionaries

    """
    return client.search_read(
        model,
        domain=domain,
        fields=fields,
        limit=limit,
        order=order,
    )


def get_record(
    client: OdooClient,
    model: str,
    record_id: int,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Get detailed record information.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        fields: List of field names to read (None = all fields)

    Returns:
        Record dictionary

    Raises:
        RecordNotFoundError: If record not found

    """
    records = client.read(model, [record_id], fields=fields)
    if not records:
        raise RecordNotFoundError(model, record_id)
    return records[0]


def list_fields(client: OdooClient, model: str) -> dict[str, Any]:
    """Get all available fields for a model.

    Args:
        client: Odoo client
        model: Model name

    Returns:
        Dictionary of field definitions with field names as keys

    """
    return client.fields_get(model)


def set_record_fields(
    client: OdooClient,
    model: str,
    record_id: int,
    values: dict[str, Any],
) -> bool:
    """Update fields on a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        values: Dictionary of field names and values to update

    Returns:
        True if successful

    Examples:
        >>> set_record_fields(client, "project.task", 42, {"name": "New title", "priority": "1"})
        >>> set_record_fields(client, "helpdesk.ticket", 42, {"user_id": 5, "stage_id": 3})

    """
    return client.write(model, [record_id], values)


def add_comment(
    client: OdooClient,
    model: str,
    record_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a record (visible to customers).

    ``user_id`` requests displayed author attribution only. Cross-user attribution
    requires an internal authenticated user; Odoo may reject or override it for share
    users, which can reliably attribute only to their own partner.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        message: Comment message (plain text or markdown)
        user_id: User whose partner is requested as author (uses default if None)
        markdown: If True, convert markdown to HTML (default: True)

    Returns:
        True if successful

    """
    body = _convert_to_html(message, markdown)
    return message_post_sudo(
        client,
        model,
        record_id,
        body,
        user_id=user_id,
        is_note=False,
    )


def add_note(
    client: OdooClient,
    model: str,
    record_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add an internal note to a record (not visible to customers).

    ``user_id`` requests displayed author attribution only. Cross-user attribution
    requires an internal authenticated user; Odoo may reject or override it for share
    users, which can reliably attribute only to their own partner.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        message: Note message (plain text or markdown)
        user_id: User whose partner is requested as author (uses default if None)
        markdown: If True, convert markdown to HTML (default: True)

    Returns:
        True if successful

    """
    body = _convert_to_html(message, markdown)
    return message_post_sudo(
        client,
        model,
        record_id,
        body,
        user_id=user_id,
        is_note=True,
    )


def _convert_to_html(text: str, use_markdown: bool = False) -> str:
    """Convert text to HTML, optionally processing markdown.

    Args:
        text: Input text
        use_markdown: If True, treat text as markdown and convert to HTML

    Returns:
        HTML string

    """
    if use_markdown:
        from vodoo.content import _markdown_to_html

        return _markdown_to_html(text)
    # Plain text - wrap in paragraph tags with newline support
    return f"<p>{text}</p>"


class _HTMLToMarkdown(_html_parser_mod.HTMLParser):
    """Simple HTML to Markdown converter."""

    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []
        self.in_bold = False
        self.in_italic = False
        self.in_code = False
        self.in_pre = False
        self.in_heading = 0
        self.in_list_item = False
        self.list_stack: list[str] = []  # Track ul/ol nesting
        self.current_href: str = ""

    def handle_starttag(  # noqa: PLR0912
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in ("b", "strong"):
            self.in_bold = True
            self.result.append("**")
        elif tag in ("i", "em"):
            self.in_italic = True
            self.result.append("*")
        elif tag == "code":
            self.in_code = True
            self.result.append("`")
        elif tag == "pre":
            self.in_pre = True
            self.result.append("\n```\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.in_heading = int(tag[1])
            self.result.append("\n" + "#" * self.in_heading + " ")
        elif tag == "br":
            self.result.append("\n")
        elif tag == "p":
            self.result.append("\n\n")
        elif tag == "a":
            self.current_href = dict(attrs).get("href") or ""
            self.result.append("[")
        elif tag == "ul":
            self.list_stack.append("ul")
            self.result.append("\n")
        elif tag == "ol":
            self.list_stack.append("ol")
            self.result.append("\n")
        elif tag == "li":
            self.in_list_item = True
            indent = "  " * (len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1] == "ul":
                self.result.append(f"{indent}- ")
            else:
                self.result.append(f"{indent}1. ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("b", "strong"):
            self.in_bold = False
            self.result.append("**")
        elif tag in ("i", "em"):
            self.in_italic = False
            self.result.append("*")
        elif tag == "code":
            self.in_code = False
            self.result.append("`")
        elif tag == "pre":
            self.in_pre = False
            self.result.append("\n```\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.in_heading = 0
            self.result.append("\n")
        elif tag == "a":
            self.result.append(f"]({self.current_href})")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self.result.append("\n")
        elif tag == "li":
            self.in_list_item = False
            self.result.append("\n")

    def handle_data(self, data: str) -> None:
        if data.strip() or self.in_pre:
            self.result.append(data)

    def get_markdown(self) -> str:
        return "".join(self.result).strip()


def _html_to_markdown(html: str) -> str:
    """Convert HTML to markdown for display.

    Args:
        html: HTML string

    Returns:
        Markdown-formatted text

    """
    # Let HTMLParser decode character references after it has identified tags.
    # Pre-unescaping would turn text such as ``&lt;placeholder&gt;`` into apparent
    # markup and silently discard it.
    parser = _HTMLToMarkdown()
    parser.feed(html)
    return parser.get_markdown()


def list_tags(client: OdooClient, model: str) -> list[dict[str, Any]]:
    """List available tags for a model.

    Args:
        client: Odoo client
        model: Tag model name (e.g., 'helpdesk.tag', 'project.tags')

    Returns:
        List of tag dictionaries

    """
    fields = _TAG_FIELDS
    return client.search_read(model, fields=fields, order="name")


def add_tag_to_record(
    client: OdooClient,
    model: str,
    record_id: int,
    tag_id: int,
) -> bool:
    """Add a tag to a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        tag_id: Tag ID

    Returns:
        True if successful

    """
    record = get_record(client, model, record_id, fields=["tag_ids"])
    current_tags = record.get("tag_ids", [])

    # Add new tag if not already present
    if tag_id not in current_tags:
        current_tags.append(tag_id)
        return client.write(
            model,
            [record_id],
            {"tag_ids": [(6, 0, current_tags)]},
        )

    return True


def list_messages(
    client: OdooClient,
    model: str,
    record_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List messages/chatter for a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        limit: Maximum number of messages (None = all)

    Returns:
        List of message dictionaries

    """
    domain = [
        ("model", "=", model),
        ("res_id", "=", record_id),
    ]
    fields = _MESSAGE_FIELDS

    return client.search_read(
        "mail.message",
        domain=domain,
        fields=fields,
        order="date desc",
        limit=limit,
    )


def list_attachments(
    client: OdooClient,
    model: str,
    record_id: int,
) -> list[dict[str, Any]]:
    """List attachments for a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID

    Returns:
        List of attachment dictionaries

    """
    domain = [
        ("res_model", "=", model),
        ("res_id", "=", record_id),
    ]
    fields = _ATTACHMENT_LIST_FIELDS

    return client.search_read("ir.attachment", domain=domain, fields=fields)


def download_attachment(
    client: OdooClient,
    attachment_id: int,
    output_path: Path | None = None,
) -> Path:
    """Download an attachment.

    Args:
        client: Odoo client
        attachment_id: Attachment ID
        output_path: Output file path (defaults to attachment name in current dir)

    Returns:
        Path to downloaded file

    Raises:
        RecordNotFoundError: If attachment not found

    """
    attachments = client.read("ir.attachment", [attachment_id], _ATTACHMENT_READ_FIELDS)

    if not attachments:
        raise RecordNotFoundError("ir.attachment", attachment_id)

    attachment = attachments[0]
    filename = attachment.get("name", f"attachment_{attachment_id}")

    if output_path is None:
        output_path = Path.cwd() / filename
    elif output_path.is_dir():
        output_path = output_path / filename

    # Decode base64 data and write to file
    if attachment.get("datas"):
        data = base64.b64decode(attachment["datas"])
        output_path.write_bytes(data)
    else:
        raise RecordNotFoundError("ir.attachment", attachment_id)

    return output_path


def download_record_attachments(
    client: OdooClient,
    model: str,
    record_id: int,
    output_dir: Path | None = None,
    extension: str | None = None,
) -> list[Path]:
    """Download all attachments for a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        output_dir: Output directory (defaults to current directory)
        extension: File extension filter (e.g., 'pdf', 'jpg')

    Returns:
        List of paths to downloaded files

    """
    if output_dir is None:
        output_dir = Path.cwd()
    elif not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    attachments = list_attachments(client, model, record_id)

    # Filter by extension if provided
    if extension:
        ext = extension.lower().lstrip(".")
        attachments = [
            att for att in attachments if att.get("name", "").lower().endswith(f".{ext}")
        ]

    downloaded_files: list[Path] = []

    for attachment in attachments:
        filename = attachment.get("name", f"attachment_{attachment['id']}")
        try:
            att_data = client.read("ir.attachment", [attachment["id"]], _ATTACHMENT_READ_FIELDS)
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
            import logging

            logging.getLogger("vodoo").warning("Failed to download %s: %s", filename, e)
            continue

    return downloaded_files


def _prepare_attachment_upload(
    file_path: Path | str | None,
    data: bytes | None,
    name: str | None,
    model: str,
    record_id: int,
) -> dict[str, Any]:
    """Validate inputs and build the ir.attachment values dict."""
    if file_path is not None and data is not None:
        msg = "Cannot specify both 'file_path' and 'data'"
        raise ValueError(msg)

    if file_path is None and data is None:
        msg = "Must specify either 'file_path' or 'data'"
        raise ValueError(msg)

    if data is not None and not name:
        msg = "'name' is required when using 'data'"
        raise ValueError(msg)

    if data is not None:
        encoded_data = base64.b64encode(data).decode("utf-8")
        attachment_name = name
    else:
        file_path = Path(file_path)  # type: ignore[arg-type]

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        if not file_path.is_file():
            msg = f"Path is not a file: {file_path}"
            raise ValueError(msg)

        file_data = file_path.read_bytes()
        encoded_data = base64.b64encode(file_data).decode("utf-8")
        attachment_name = name or file_path.name

    return {
        "name": attachment_name,
        "datas": encoded_data,
        "res_model": model,
        "res_id": record_id,
    }


def get_attachment_data(
    client: OdooClient,
    attachment_id: int,
) -> bytes:
    """Read an attachment and return its raw binary content.

    Unlike :func:`download_attachment`, the file is never written to disk;
    the decoded bytes are returned directly.

    Args:
        client: Odoo client
        attachment_id: Attachment ID

    Returns:
        Raw bytes of the attachment

    Raises:
        RecordNotFoundError: If attachment not found or has no data

    """
    attachments = client.read("ir.attachment", [attachment_id], _ATTACHMENT_READ_FIELDS)
    if not attachments:
        raise RecordNotFoundError("ir.attachment", attachment_id)

    return _decode_attachment_data(attachments[0], attachment_id)


def get_record_attachment_data(
    client: OdooClient,
    model: str,
    record_id: int,
) -> list[tuple[int, str, bytes]]:
    """Read all attachments for a record and return their binary content.

    Unlike :func:`download_record_attachments`, files are never written to
    disk; each attachment's decoded bytes are returned in-memory.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID

    Returns:
        List of ``(attachment_id, filename, data)`` tuples.
        Attachments with empty or missing ``datas`` are silently skipped.

    """
    attachments = list_attachments(client, model, record_id)

    result: list[tuple[int, str, bytes]] = []
    for att_meta in attachments:
        att_id = att_meta["id"]
        try:
            att_data = client.read("ir.attachment", [att_id], ["id", *_ATTACHMENT_READ_FIELDS])
            if not att_data:
                continue
            decoded = _decode_attachment_record(att_data[0], att_id)
            if decoded is not None:
                result.append(decoded)
        except Exception:
            continue

    return result


def create_attachment(
    client: OdooClient,
    model: str,
    record_id: int,
    file_path: Path | str | None = None,
    *,
    data: bytes | None = None,
    name: str | None = None,
) -> int:
    """Create an attachment for a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        file_path: Path to file to attach (mutually exclusive with data)
        data: Raw bytes to attach (mutually exclusive with file_path)
        name: Attachment name (defaults to filename; required when using data)

    Returns:
        ID of created attachment

    Raises:
        ValueError: If arguments are invalid
        FileNotFoundError: If file path is invalid

    Examples:
        >>> create_attachment(client, "project.task", 42, "screenshot.png")
        >>> create_attachment(client, "helpdesk.ticket", 42, "/path/to/file.pdf", name="Report.pdf")
        >>> create_attachment(client, "project.task", 42, data=b"content", name="doc.txt")

    """
    values = _prepare_attachment_upload(file_path, data, name, model, record_id)
    return client.create("ir.attachment", values)


def get_record_url(client: OdooClient | Any, model: str, record_id: int) -> str:
    """Get the web URL for a record.

    Uses the canonical path URL for a selected JSON-2 transport and the
    legacy hash URL otherwise. Works with sync and async clients without
    making an additional request.

    Args:
        client: Odoo client (sync or async)
        model: Model name
        record_id: Record ID

    Returns:
        URL to view the record in Odoo web interface

    Examples:
        >>> get_record_url(client, "helpdesk.ticket", 42)
        'https://odoo.example.com/web#id=42&model=helpdesk.ticket&view_type=form'

    """
    return build_record_url(
        client.config.url,
        model,
        record_id,
        "json2" if getattr(client, "is_json2", False) else "jsonrpc",
    )


# Deprecated presentation compatibility shims. Importing ``vodoo.base`` remains
# terminal-independent; the CLI presentation package is loaded only when one
# of these historical helpers is called.
def _cli_output() -> Any:
    from vodoo.cli import output

    return output


def _cli_display() -> Any:
    from vodoo.cli import display

    return display


def configure_output(
    *,
    console: Any = None,
    simple: bool = False,
    json_mode: bool = False,
    toon_mode: bool = False,
) -> None:
    """Deprecated compatibility shim for :func:`vodoo.cli.output.configure_output`."""
    _cli_output().configure_output(
        console=console,
        simple=simple,
        json_mode=json_mode,
        toon_mode=toon_mode,
    )


def _get_console() -> Any:
    """Deprecated compatibility shim for the active CLI console."""
    return _cli_output().get_console()


def _is_simple_output() -> bool:
    """Deprecated compatibility shim for the active CLI mode."""
    return bool(_cli_output().is_simple_output())


def is_json_output() -> bool:
    """Deprecated compatibility shim for the active CLI mode."""
    return bool(_cli_output().is_json_output())


def is_toon_output() -> bool:
    """Deprecated compatibility shim for the active CLI mode."""
    return bool(_cli_output().is_toon_output())


def is_structured_output() -> bool:
    """Deprecated compatibility shim for the active CLI mode."""
    return bool(_cli_output().is_structured_output())


def json_print(data: Any) -> None:
    """Deprecated compatibility shim for JSON rendering."""
    _cli_output().json_print(data)


def toon_print(data: Any) -> None:
    """Deprecated compatibility shim for TOON rendering."""
    _cli_output().toon_print(data)


def structured_print(data: Any) -> None:
    """Deprecated compatibility shim for structured rendering."""
    _cli_output().structured_print(data)


def _format_field_value(value: Any) -> str:
    """Deprecated compatibility shim for CLI field formatting."""
    return str(_cli_display()._format_field_value(value))


def display_records(records: list[dict[str, Any]], title: str = "Records") -> None:
    """Deprecated compatibility shim for CLI record rendering."""
    _cli_display().display_records(records, title)


def display_record_detail(
    record: dict[str, Any],
    *,
    show_html: bool = False,
    record_type: str = "Record",
) -> None:
    """Deprecated compatibility shim for CLI record-detail rendering."""
    _cli_display().display_record_detail(
        record,
        show_html=show_html,
        record_type=record_type,
    )


def display_tags(tags: list[dict[str, Any]], title: str = "Tags") -> None:
    """Deprecated compatibility shim for CLI tag rendering."""
    _cli_display().display_tags(tags, title)


def display_messages(messages: list[dict[str, Any]], show_html: bool = False) -> None:
    """Deprecated compatibility shim for CLI message rendering."""
    _cli_display().display_messages(messages, show_html)


def display_attachments(attachments: list[dict[str, Any]]) -> None:
    """Deprecated compatibility shim for CLI attachment rendering."""
    _cli_display().display_attachments(attachments)
