"""Base operations for Odoo models - shared functionality."""

from __future__ import annotations

import base64
import html.parser as _html_parser_mod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vodoo.auth import message_post_sudo
from vodoo.client import OdooClient
from vodoo.exceptions import RecordNotFoundError

if TYPE_CHECKING:
    from rich.console import Console

# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------
# The CLI layer (main.py) calls ``configure_output()`` to set the active
# console and simple-output flag.  When Vodoo is used as a library these
# defaults are used instead, so no import of main.py is needed.
#
# These are module-level globals rather than contextvars.  Concurrent output
# configurations in the same process would stomp each other, but that scenario
# is unrealistic: the Odoo server itself is the shared mutable state, so tests
# and CLI sessions are inherently sequential.

# Field lists shared with aio.base
_TAG_FIELDS: list[str] = ["id", "name", "color"]
_MESSAGE_FIELDS: list[str] = [
    "id", "date", "author_id", "body", "subject",
    "message_type", "subtype_id", "email_from",
]
_ATTACHMENT_LIST_FIELDS: list[str] = ["id", "name", "file_size", "mimetype", "create_date"]
_ATTACHMENT_READ_FIELDS: list[str] = ["name", "datas"]

_output_console: Console | None = None
_output_simple: bool = False


def configure_output(*, console: Console | None = None, simple: bool = False) -> None:
    """Configure the output console and mode.

    Called by the CLI layer.  Library users may call this to customise
    display behaviour, or simply ignore it (sensible defaults apply).

    Requires the ``cli`` extra (``rich``) when *console* is provided or
    *simple* is ``False`` and display functions are subsequently called.

    Args:
        console: Rich Console instance to use for output.
        simple: If ``True``, display functions emit plain TSV instead of
            rich tables.

    """
    global _output_console, _output_simple  # noqa: PLW0603
    if console is not None:
        _output_console = console
    _output_simple = simple


def _get_console() -> Console:
    """Return the currently configured console, creating one if needed."""
    global _output_console  # noqa: PLW0603
    if _output_console is None:
        from rich.console import Console as _Console

        _output_console = _Console()
    return _output_console


def _is_simple_output() -> bool:
    """Return ``True`` when plain/TSV output is requested."""
    return _output_simple


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


def _format_field_value(value: Any) -> str:
    """Format a field value for display.

    Args:
        value: Field value from Odoo

    Returns:
        Formatted string

    """
    if value is False or value is None:
        return ""
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], int):
        # Many2one field [id, name]
        return str(value[1])
    if isinstance(value, list):
        # Many2many or one2many field
        return ",".join(str(v) for v in value)
    return str(value)


def display_records(records: list[dict[str, Any]], title: str = "Records") -> None:
    """Display records in a table or TSV format.

    Args:
        records: List of record dictionaries
        title: Table title

    """
    if not records:
        if _is_simple_output():
            print("No records found")
        else:
            _get_console().print("[yellow]No records found[/yellow]")
        return

    field_names = list(records[0].keys())

    if _is_simple_output():
        # Simple TSV output for LLMs
        print("\t".join(field_names))
        for record in records:
            row = [_format_field_value(record.get(f)) for f in field_names]
            print("\t".join(row))
    else:
        # Rich table output
        from rich.table import Table

        console = _get_console()
        table = Table(title=title)

        field_styles = {
            "id": "cyan",
            "name": "green",
            "partner_id": "yellow",
            "stage_id": "blue",
            "user_id": "magenta",
            "priority": "red",
            "project_id": "blue",
        }

        for field_name in field_names:
            style = field_styles.get(field_name, "white")
            table.add_column(field_name, style=style)

        for record in records:
            row_values = [_format_field_value(record.get(f)) or "N/A" for f in field_names]
            table.add_row(*row_values)

        console.print(table)


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
    result: dict[str, Any] = client.execute(model, "fields_get")
    return result


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


def display_record_detail(  # noqa: PLR0912
    record: dict[str, Any],
    *,
    show_html: bool = False,
    record_type: str = "Record",
) -> None:
    """Display detailed record information.

    Args:
        record: Record dictionary
        show_html: If True, show raw HTML description, else convert to markdown
        record_type: Human-readable record type (e.g., "Ticket", "Task")

    """
    if _is_simple_output():
        # Simple key: value format
        print(f"id: {record['id']}")
        print(f"name: {record['name']}")
        if record.get("partner_id"):
            print(f"partner: {record['partner_id'][1]}")
        if record.get("stage_id"):
            print(f"stage: {record['stage_id'][1]}")
        if record.get("user_id"):
            print(f"assigned_to: {record['user_id'][1]}")
        if record.get("project_id"):
            print(f"project: {record['project_id'][1]}")
        if "priority" in record:
            print(f"priority: {record.get('priority', '0')}")
        if record.get("description"):
            desc = record["description"]
            if not show_html:
                desc = _html_to_markdown(desc)
            print(f"description: {desc}")
        if record.get("tag_ids"):
            print(f"tags: {','.join(map(str, record['tag_ids']))}")
    else:
        console = _get_console()
        console.print(f"\n[bold cyan]{record_type} #{record['id']}[/bold cyan]")
        console.print(f"[bold]Name:[/bold] {record['name']}")

        if record.get("partner_id"):
            console.print(f"[bold]Partner:[/bold] {record['partner_id'][1]}")

        if record.get("stage_id"):
            console.print(f"[bold]Stage:[/bold] {record['stage_id'][1]}")

        if record.get("user_id"):
            console.print(f"[bold]Assigned To:[/bold] {record['user_id'][1]}")

        if record.get("project_id"):
            console.print(f"[bold]Project:[/bold] {record['project_id'][1]}")

        if "priority" in record:
            console.print(f"[bold]Priority:[/bold] {record.get('priority', '0')}")

        if record.get("description"):
            description = record["description"]
            if show_html:
                console.print(f"\n[bold]Description:[/bold]\n{description}")
            else:
                markdown_text = _html_to_markdown(description)
                console.print(f"\n[bold]Description:[/bold]\n{markdown_text}")

        if record.get("tag_ids"):
            console.print(f"\n[bold]Tags:[/bold] {', '.join(map(str, record['tag_ids']))}")


def add_comment(
    client: OdooClient,
    model: str,
    record_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a record (visible to customers).

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        message: Comment message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
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

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        message: Note message (plain text or markdown)
        user_id: User ID to post as (uses default if None)
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
    from html import unescape

    parser = _HTMLToMarkdown()
    parser.feed(unescape(html))
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


def display_tags(tags: list[dict[str, Any]], title: str = "Tags") -> None:
    """Display tags in a table or TSV format.

    Args:
        tags: List of tag dictionaries
        title: Table title

    """
    if _is_simple_output():
        print("id\tname\tcolor")
        for tag in tags:
            print(f"{tag['id']}\t{tag['name']}\t{tag.get('color', '')}")
    else:
        from rich.table import Table

        console = _get_console()
        table = Table(title=title)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Color", style="yellow")

        for tag in tags:
            table.add_row(
                str(tag["id"]),
                tag["name"],
                str(tag.get("color", "N/A")),
            )

        console.print(table)


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


def display_messages(messages: list[dict[str, Any]], show_html: bool = False) -> None:  # noqa: PLR0912
    """Display messages in a formatted list or simple format.

    Args:
        messages: List of message dictionaries
        show_html: Whether to show raw HTML body

    """
    from html import unescape
    from html.parser import HTMLParser

    class HTMLToText(HTMLParser):
        """Simple HTML to text converter."""

        def __init__(self) -> None:
            super().__init__()
            self.text: list[str] = []

        def handle_data(self, data: str) -> None:
            self.text.append(data)

        def get_text(self) -> str:
            return "".join(self.text).strip()

    def get_body_text(body: str) -> str:
        if show_html:
            return body
        parser = HTMLToText()
        parser.feed(unescape(body))
        return parser.get_text()

    if not messages:
        print("No messages found") if _is_simple_output() else _get_console().print(
            "[yellow]No messages found[/yellow]"
        )
        return

    if _is_simple_output():
        # Simple format: date, author, type, body (one line per message)
        print("date\tauthor\ttype\tbody")
        for msg in messages:
            date = msg.get("date", "")
            author = msg.get("author_id")
            author_name = (
                author[1] if author and isinstance(author, list) else msg.get("email_from", "")
            )
            subtype = msg.get("subtype_id")
            if subtype and isinstance(subtype, list):
                subtype_name = subtype[1]
            else:
                subtype_name = msg.get("message_type", "")
            body = get_body_text(msg.get("body", "")).replace("\t", " ").replace("\n", " ")
            print(f"{date}\t{author_name}\t{subtype_name}\t{body}")
    else:
        console = _get_console()
        console.print(f"\n[bold cyan]Message History ({len(messages)} messages)[/bold cyan]\n")

        for i, msg in enumerate(messages, 1):
            date = msg.get("date", "N/A")
            author = msg.get("author_id")
            if author and isinstance(author, list):
                author_name = author[1]
            else:
                author_name = msg.get("email_from", "Unknown")

            message_type = msg.get("message_type", "comment")
            subtype = msg.get("subtype_id")
            subtype_name = subtype[1] if subtype and isinstance(subtype, list) else message_type

            console.print(f"[bold]Message #{i}[/bold] [dim]({date})[/dim]")
            console.print(f"[cyan]From:[/cyan] {author_name}")
            console.print(f"[cyan]Type:[/cyan] {subtype_name}")

            if msg.get("subject"):
                console.print(f"[cyan]Subject:[/cyan] {msg['subject']}")

            body = msg.get("body", "")
            if body:
                text = get_body_text(body)
                if text:
                    console.print(f"\n{text}\n")

            if i < len(messages):
                console.print("[dim]" + "─" * 80 + "[/dim]\n")


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


def display_attachments(attachments: list[dict[str, Any]]) -> None:
    """Display attachments in a table or TSV format.

    Args:
        attachments: List of attachment dictionaries

    """
    if _is_simple_output():
        print("id\tname\tsize_kb\tmimetype\tcreate_date")
        for att in attachments:
            size = att.get("file_size", 0)
            size_kb = f"{size / 1024:.1f}" if size else ""
            name = att.get("name", "")
            mime = att.get("mimetype", "")
            created = att.get("create_date", "")
            print(f"{att['id']}\t{name}\t{size_kb}\t{mime}\t{created}")
    else:
        from rich.table import Table

        console = _get_console()
        table = Table(title="Attachments")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Size", style="yellow")
        table.add_column("Type", style="blue")
        table.add_column("Created", style="magenta")

        for att in attachments:
            size = att.get("file_size", 0)
            size_str = f"{size / 1024:.1f} KB" if size else "N/A"

            table.add_row(
                str(att["id"]),
                att.get("name", "N/A"),
                size_str,
                att.get("mimetype", "N/A"),
                str(att.get("create_date", "N/A")),
            )

        console.print(table)


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


def create_attachment(
    client: OdooClient,
    model: str,
    record_id: int,
    file_path: Path | str,
    name: str | None = None,
) -> int:
    """Create an attachment for a record.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        file_path: Path to file to attach
        name: Attachment name (defaults to filename)

    Returns:
        ID of created attachment

    Raises:
        ValueError: If file doesn't exist
        FileNotFoundError: If file path is invalid

    Examples:
        >>> create_attachment(client, "project.task", 42, "screenshot.png")
        >>> create_attachment(client, "helpdesk.ticket", 42, "/path/to/file.pdf", name="Report.pdf")

    """
    file_path = Path(file_path)

    if not file_path.exists():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    if not file_path.is_file():
        msg = f"Path is not a file: {file_path}"
        raise ValueError(msg)

    # Read file and encode to base64
    file_data = file_path.read_bytes()
    encoded_data = base64.b64encode(file_data).decode("utf-8")

    # Use provided name or file name
    attachment_name = name or file_path.name

    # Create attachment
    values = {
        "name": attachment_name,
        "datas": encoded_data,
        "res_model": model,
        "res_id": record_id,
    }

    return client.create("ir.attachment", values)


def get_record_url(client: OdooClient | Any, model: str, record_id: int) -> str:
    """Get the web URL for a record.

    Works with both sync ``OdooClient`` and async ``AsyncOdooClient`` —
    only ``client.config.url`` is accessed.

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
    base_url = client.config.url.rstrip("/")
    return f"{base_url}/web#id={record_id}&model={model}&view_type=form"
