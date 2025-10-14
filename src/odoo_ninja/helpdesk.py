"""Helpdesk operations for Odoo Ninja."""

import base64
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from odoo_ninja.auth import message_post_sudo
from odoo_ninja.client import OdooClient

console = Console()


def list_tickets(
    client: OdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
) -> list[dict[str, Any]]:
    """List helpdesk tickets.

    Args:
        client: Odoo client
        domain: Search domain filters
        limit: Maximum number of tickets

    Returns:
        List of ticket dictionaries

    """
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
    table = Table(title="Helpdesk Tickets")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Partner", style="yellow")
    table.add_column("Stage", style="blue")
    table.add_column("Assigned To", style="magenta")
    table.add_column("Priority", style="red")

    for ticket in tickets:
        partner = ticket["partner_id"][1] if ticket.get("partner_id") else "N/A"
        stage = ticket["stage_id"][1] if ticket.get("stage_id") else "N/A"
        user = ticket["user_id"][1] if ticket.get("user_id") else "Unassigned"

        table.add_row(
            str(ticket["id"]),
            ticket["name"],
            partner,
            stage,
            user,
            ticket.get("priority", "0"),
        )

    console.print(table)


def get_ticket(client: OdooClient, ticket_id: int) -> dict[str, Any]:
    """Get detailed ticket information.

    Args:
        client: Odoo client
        ticket_id: Ticket ID

    Returns:
        Ticket dictionary

    Raises:
        ValueError: If ticket not found

    """
    tickets = client.read("helpdesk.ticket", [ticket_id])
    if not tickets:
        msg = f"Ticket {ticket_id} not found"
        raise ValueError(msg)
    return tickets[0]


def display_ticket_detail(ticket: dict[str, Any]) -> None:
    """Display detailed ticket information.

    Args:
        ticket: Ticket dictionary

    """
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
) -> bool:
    """Add a comment to a ticket (visible to customers).

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        message: Comment message
        user_id: User ID to post as (uses default if None)

    Returns:
        True if successful

    """
    return message_post_sudo(
        client,
        "helpdesk.ticket",
        ticket_id,
        message,
        user_id=user_id,
        is_note=False,
    )


def add_note(
    client: OdooClient,
    ticket_id: int,
    message: str,
    user_id: int | None = None,
) -> bool:
    """Add an internal note to a ticket (not visible to customers).

    Args:
        client: Odoo client
        ticket_id: Ticket ID
        message: Note message
        user_id: User ID to post as (uses default if None)

    Returns:
        True if successful

    """
    return message_post_sudo(
        client,
        "helpdesk.ticket",
        ticket_id,
        message,
        user_id=user_id,
        is_note=True,
    )


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
    data = base64.b64decode(attachment["datas"])
    output_path.write_bytes(data)

    return output_path
