"""Main CLI application for Odoo Ninja."""

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from odoo_ninja.client import OdooClient
from odoo_ninja.config import get_config
from odoo_ninja.helpdesk import (
    add_comment,
    add_note,
    add_tag_to_ticket,
    display_attachments,
    display_tags,
    display_ticket_detail,
    display_tickets,
    download_attachment,
    get_ticket,
    list_attachments,
    list_tags,
    list_tickets,
)

app = typer.Typer(
    name="odoo-ninja",
    help="CLI tool for accessing Odoo helpdesk tickets",
    no_args_is_help=True,
)

helpdesk_app = typer.Typer(
    name="helpdesk",
    help="Helpdesk ticket operations",
    no_args_is_help=True,
)
app.add_typer(helpdesk_app, name="helpdesk")

console = Console()


def get_client() -> OdooClient:
    """Get configured Odoo client.

    Returns:
        OdooClient instance

    """
    config = get_config()
    return OdooClient(config)


@helpdesk_app.command("list")
def helpdesk_list(
    stage: Annotated[str | None, typer.Option(help="Filter by stage name")] = None,
    partner: Annotated[str | None, typer.Option(help="Filter by partner name")] = None,
    assigned_to: Annotated[str | None, typer.Option(help="Filter by assigned user name")] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of tickets")] = 50,
) -> None:
    """List helpdesk tickets."""
    client = get_client()

    # Build domain filters
    domain: list[Any] = []
    if stage:
        domain.append(("stage_id.name", "ilike", stage))
    if partner:
        domain.append(("partner_id.name", "ilike", partner))
    if assigned_to:
        domain.append(("user_id.name", "ilike", assigned_to))

    try:
        tickets = list_tickets(client, domain=domain, limit=limit)
        display_tickets(tickets)
        console.print(f"\n[dim]Found {len(tickets)} tickets[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("show")
def helpdesk_show(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
) -> None:
    """Show detailed ticket information."""
    client = get_client()

    try:
        ticket = get_ticket(client, ticket_id)
        display_ticket_detail(ticket)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("comment")
def helpdesk_comment(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    message: Annotated[str, typer.Argument(help="Comment message")],
    user_id: Annotated[
        int | None, typer.Option(help="User ID to post as (uses default if not set)")
    ] = None,
) -> None:
    """Add a comment to a ticket (visible to customers)."""
    client = get_client()

    # Check if harmful operations are allowed
    if not client.config.allow_harmful_operations:
        console.print(
            "[red]Error:[/red] Posting public comments is disabled. "
            "This is a harmful operation (visible to customers).\n"
            "To enable, set ODOO_ALLOW_HARMFUL_OPERATIONS=true in your .env file.\n"
            "For internal notes (safe), use: [cyan]odoo-ninja helpdesk note[/cyan]"
        )
        raise typer.Exit(1)

    try:
        success = add_comment(client, ticket_id, message, user_id=user_id)
        if success:
            console.print(f"[green]Successfully added comment to ticket {ticket_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to ticket {ticket_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("note")
def helpdesk_note(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    message: Annotated[str, typer.Argument(help="Note message")],
    user_id: Annotated[
        int | None, typer.Option(help="User ID to post as (uses default if not set)")
    ] = None,
) -> None:
    """Add an internal note to a ticket (not visible to customers)."""
    client = get_client()

    try:
        success = add_note(client, ticket_id, message, user_id=user_id)
        if success:
            console.print(f"[green]Successfully added note to ticket {ticket_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to ticket {ticket_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("tags")
def helpdesk_tags() -> None:
    """List available helpdesk tags."""
    client = get_client()

    try:
        tags = list_tags(client)
        display_tags(tags)
        console.print(f"\n[dim]Found {len(tags)} tags[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("tag")
def helpdesk_tag(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    tag_id: Annotated[int, typer.Argument(help="Tag ID")],
) -> None:
    """Add a tag to a ticket."""
    client = get_client()

    try:
        add_tag_to_ticket(client, ticket_id, tag_id)
        console.print(f"[green]Successfully added tag {tag_id} to ticket {ticket_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("attachments")
def helpdesk_attachments(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
) -> None:
    """List attachments for a ticket."""
    client = get_client()

    try:
        attachments = list_attachments(client, ticket_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for ticket {ticket_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("download")
def helpdesk_download(
    attachment_id: Annotated[int, typer.Argument(help="Attachment ID")],
    output: Annotated[
        Path | None,
        typer.Option(help="Output file path (defaults to attachment name)"),
    ] = None,
) -> None:
    """Download an attachment."""
    client = get_client()

    try:
        output_path = download_attachment(client, attachment_id, output)
        console.print(f"[green]Downloaded attachment to {output_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
