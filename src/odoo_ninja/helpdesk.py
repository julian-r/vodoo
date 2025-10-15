"""Helpdesk operations for Odoo Ninja."""

import base64
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.table import Table

from odoo_ninja.auth import message_post_sudo
from odoo_ninja.client import OdooClient

if TYPE_CHECKING:
    from rich.console import Console


def _get_console() -> "Console":
    """Get console instance from main module.

    Returns:
        Console instance

    """
    from odoo_ninja.main import console

    return console


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
        fields = [
            "id",
            "name",
            "partner_id",
            "stage_id",
            "user_id",
            "priority",
            "tag_ids",
            "create_date",
        ]

    return client.search_read(
        "helpdesk.ticket",
        domain=domain,
        fields=fields,
        limit=limit,
        order="create_date desc",
    )


def display_tickets(tickets: list[dict[str, Any]]) -> None:
    """Display tickets in a rich table.

    Args:
        tickets: List of ticket dictionaries

    """
    console = _get_console()
    if not tickets:
        console.print("[yellow]No tickets found[/yellow]")
        return

    table = Table(title="Helpdesk Tickets")

    # Get all field names from the first ticket
    field_names = list(tickets[0].keys())

    # Add columns for each field with styling
    field_styles = {
        "id": "cyan",
        "name": "green",
        "partner_id": "yellow",
        "stage_id": "blue",
        "user_id": "magenta",
        "priority": "red",
    }

    for field_name in field_names:
        style = field_styles.get(field_name, "white")
        table.add_column(field_name, style=style)

    # Add rows
    for ticket in tickets:
        row_values = []
        for field_name in field_names:
            value = ticket.get(field_name)

            # Format the value
            if value is False or value is None:
                formatted_value = "N/A"
            elif isinstance(value, list) and len(value) == 2 and isinstance(value[0], int):
                # Many2one field [id, name]
                formatted_value = value[1]
            elif isinstance(value, list):
                # Many2many or one2many field
                formatted_value = str(value)
            else:
                formatted_value = str(value)

            row_values.append(formatted_value)

        table.add_row(*row_values)

    console.print(table)


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
    tickets = client.read("helpdesk.ticket", [ticket_id], fields=fields)
    if not tickets:
        msg = f"Ticket {ticket_id} not found"
        raise ValueError(msg)
    return tickets[0]


def list_ticket_fields(client: OdooClient) -> dict[str, Any]:
    """Get all available fields for helpdesk tickets.

    Args:
        client: Odoo client

    Returns:
        Dictionary of field definitions with field names as keys

    """
    return client.execute("helpdesk.ticket", "fields_get")


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
    return client.write("helpdesk.ticket", [ticket_id], values)


def display_ticket_detail(ticket: dict[str, Any]) -> None:
    """Display detailed ticket information.

    Args:
        ticket: Ticket dictionary

    """
    console = _get_console()
    console.print(f"\n[bold cyan]Ticket #{ticket['id']}[/bold cyan]")
    console.print(f"[bold]Name:[/bold] {ticket['name']}")

    if ticket.get("partner_id"):
        console.print(f"[bold]Partner:[/bold] {ticket['partner_id'][1]}")

    if ticket.get("stage_id"):
        console.print(f"[bold]Stage:[/bold] {ticket['stage_id'][1]}")

    if ticket.get("user_id"):
        console.print(f"[bold]Assigned To:[/bold] {ticket['user_id'][1]}")

    console.print(f"[bold]Priority:[/bold] {ticket.get('priority', '0')}")

    if ticket.get("description"):
        console.print(f"\n[bold]Description:[/bold]\n{ticket['description']}")

    if ticket.get("tag_ids"):
        console.print(f"\n[bold]Tags:[/bold] {', '.join(map(str, ticket['tag_ids']))}")


def add_comment(
    client: OdooClient,
    ticket_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = False,
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
    body = _convert_to_html(message, markdown)
    return message_post_sudo(
        client,
        "helpdesk.ticket",
        ticket_id,
        body,
        user_id=user_id,
        is_note=False,
    )


def add_note(
    client: OdooClient,
    ticket_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = False,
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
    body = _convert_to_html(message, markdown)
    return message_post_sudo(
        client,
        "helpdesk.ticket",
        ticket_id,
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
        import markdown

        return markdown.markdown(
            text,
            extensions=["extra", "nl2br", "sane_lists"],
        )
    # Plain text - wrap in paragraph tags with newline support
    return f"<p>{text}</p>"


def list_tags(client: OdooClient) -> list[dict[str, Any]]:
    """List available helpdesk tags.

    Args:
        client: Odoo client

    Returns:
        List of tag dictionaries

    """
    fields = ["id", "name", "color"]
    return client.search_read("helpdesk.tag", fields=fields, order="name")


def display_tags(tags: list[dict[str, Any]]) -> None:
    """Display tags in a rich table.

    Args:
        tags: List of tag dictionaries

    """
    console = _get_console()
    table = Table(title="Helpdesk Tags")
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
    # Get current tags
    ticket = get_ticket(client, ticket_id)
    current_tags = ticket.get("tag_ids", [])

    # Add new tag if not already present
    if tag_id not in current_tags:
        current_tags.append(tag_id)
        return client.write(
            "helpdesk.ticket",
            [ticket_id],
            {"tag_ids": [(6, 0, current_tags)]},
        )

    return True


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
    domain = [
        ("model", "=", "helpdesk.ticket"),
        ("res_id", "=", ticket_id),
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

    return client.search_read(
        "mail.message",
        domain=domain,
        fields=fields,
        order="date desc",
        limit=limit,
    )


def display_messages(messages: list[dict[str, Any]], show_html: bool = False) -> None:
    """Display messages in a formatted list.

    Args:
        messages: List of message dictionaries
        show_html: Whether to show raw HTML body

    """
    from html import unescape
    from html.parser import HTMLParser

    console = _get_console()

    class HTMLToText(HTMLParser):
        """Simple HTML to text converter."""

        def __init__(self) -> None:
            super().__init__()
            self.text: list[str] = []

        def handle_data(self, data: str) -> None:
            self.text.append(data)

        def get_text(self) -> str:
            return "".join(self.text).strip()

    if not messages:
        console.print("[yellow]No messages found[/yellow]")
        return

    console.print(f"\n[bold cyan]Message History ({len(messages)} messages)[/bold cyan]\n")

    for i, msg in enumerate(messages, 1):
        # Message header
        date = msg.get("date", "N/A")
        author = msg.get("author_id")
        author_name = (
            author[1] if author and isinstance(author, list) else msg.get("email_from", "Unknown")
        )

        message_type = msg.get("message_type", "comment")
        subtype = msg.get("subtype_id")
        subtype_name = subtype[1] if subtype and isinstance(subtype, list) else message_type

        console.print(f"[bold]Message #{i}[/bold] [dim]({date})[/dim]")
        console.print(f"[cyan]From:[/cyan] {author_name}")
        console.print(f"[cyan]Type:[/cyan] {subtype_name}")

        if msg.get("subject"):
            console.print(f"[cyan]Subject:[/cyan] {msg['subject']}")

        # Message body
        body = msg.get("body", "")
        if body:
            if show_html:
                console.print(f"\n{body}\n")
            else:
                # Convert HTML to plain text
                parser = HTMLToText()
                parser.feed(unescape(body))
                text = parser.get_text()
                if text:
                    console.print(f"\n{text}\n")

        if i < len(messages):
            console.print("[dim]" + "─" * 80 + "[/dim]\n")


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
    domain = [
        ("res_model", "=", "helpdesk.ticket"),
        ("res_id", "=", ticket_id),
    ]
    fields = ["id", "name", "file_size", "mimetype", "create_date"]

    return client.search_read("ir.attachment", domain=domain, fields=fields)


def display_attachments(attachments: list[dict[str, Any]]) -> None:
    """Display attachments in a rich table.

    Args:
        attachments: List of attachment dictionaries

    """
    console = _get_console()
    table = Table(title="Ticket Attachments")
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
        ValueError: If attachment not found

    """
    attachments = client.read("ir.attachment", [attachment_id], ["name", "datas"])

    if not attachments:
        msg = f"Attachment {attachment_id} not found"
        raise ValueError(msg)

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
        msg = f"Attachment {attachment_id} has no data"
        raise ValueError(msg)

    return output_path


def download_ticket_attachments(
    client: OdooClient,
    ticket_id: int,
    output_dir: Path | None = None,
    extension: str | None = None,
) -> list[Path]:
    """Download all attachments for a ticket.

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        output_dir: Output directory (defaults to current directory)
        extension: File extension filter (e.g., 'pdf', 'jpg')

    Returns:
        List of paths to downloaded files

    """
    if output_dir is None:
        output_dir = Path.cwd()
    elif not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    attachments = list_attachments(client, ticket_id)

    # Filter by extension if provided
    if extension:
        ext = extension.lower().lstrip(".")
        attachments = [
            att for att in attachments
            if att.get("name", "").lower().endswith(f".{ext}")
        ]

    downloaded_files = []

    for attachment in attachments:
        try:
            # Read the full attachment with data
            att_data = client.read("ir.attachment", [attachment["id"]], ["name", "datas"])
            if not att_data:
                continue

            att = att_data[0]
            filename = att.get("name", f"attachment_{attachment['id']}")
            output_path = output_dir / filename

            # Decode base64 data and write to file
            if att.get("datas"):
                data = base64.b64decode(att["datas"])
                output_path.write_bytes(data)
                downloaded_files.append(output_path)
        except Exception as e:
            console = _get_console()
            console.print(f"[yellow]Warning: Failed to download {filename}: {e}[/yellow]")
            continue

    return downloaded_files
