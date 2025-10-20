"""Main CLI application for Odoo Ninja."""

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from odoo_ninja.base import display_attachments, display_messages, download_attachment
from odoo_ninja.client import OdooClient
from odoo_ninja.config import get_config
from odoo_ninja.helpdesk import (
    add_comment,
    add_note,
    add_tag_to_ticket,
    create_attachment,
    display_tags,
    display_ticket_detail,
    display_tickets,
    download_ticket_attachments,
    get_ticket,
    get_ticket_url,
    list_attachments,
    list_messages,
    list_tags,
    list_ticket_fields,
    list_tickets,
    set_ticket_fields,
)
from odoo_ninja.project import (
    add_comment as add_task_comment,
)
from odoo_ninja.project import (
    add_note as add_task_note,
)
from odoo_ninja.project import (
    add_tag_to_task,
    create_task_attachment,
    display_task_detail,
    display_task_tags,
    display_tasks,
    download_task_attachments,
    get_task,
    get_task_url,
    list_task_attachments,
    list_task_fields,
    list_task_messages,
    list_task_tags,
    list_tasks,
    set_task_fields,
)
from odoo_ninja.project_project import (
    add_comment as add_project_comment,
)
from odoo_ninja.project_project import (
    add_note as add_project_note,
)
from odoo_ninja.project_project import (
    create_project_attachment,
    display_project_detail,
    display_projects,
    get_project,
    get_project_url,
    list_project_attachments,
    list_project_fields,
    list_project_messages,
    list_projects,
    set_project_fields,
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

project_task_app = typer.Typer(
    name="project-task",
    help="Project task operations",
    no_args_is_help=True,
)
app.add_typer(project_task_app, name="project-task")

project_project_app = typer.Typer(
    name="project",
    help="Project operations",
    no_args_is_help=True,
)
app.add_typer(project_project_app, name="project")

# Global state for console configuration
_console_config = {"no_color": False}

console = Console()


def get_console() -> Console:
    """Get console instance with current configuration.

    Returns:
        Console instance

    """
    no_color = _console_config["no_color"]
    return Console(force_terminal=not no_color, no_color=no_color)


@app.callback()
def main_callback(
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable colored output for programmatic use"),
    ] = False,
) -> None:
    """Global options for odoo-ninja CLI."""
    _console_config["no_color"] = no_color
    global console  # noqa: PLW0603
    console = get_console()


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
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch (can be used multiple times)"),
    ] = None,
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
        tickets = list_tickets(client, domain=domain, limit=limit, fields=fields)
        display_tickets(tickets)
        console.print(f"\n[dim]Found {len(tickets)} tickets[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("show")
def helpdesk_show(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch (can be used multiple times)"),
    ] = None,
    show_html: Annotated[
        bool,
        typer.Option("--html", help="Show raw HTML description instead of markdown"),
    ] = False,
) -> None:
    """Show detailed ticket information."""
    client = get_client()

    try:
        ticket = get_ticket(client, ticket_id, fields=fields)

        if fields:
            # If specific fields requested, show them directly
            console.print(f"\n[bold cyan]Ticket #{ticket_id}[/bold cyan]\n")
            for key, value in sorted(ticket.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_ticket_detail(ticket, show_html=show_html)
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
    markdown: Annotated[
        bool,
        typer.Option("--markdown", "-m", help="Treat message as markdown and convert to HTML"),
    ] = False,
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
        success = add_comment(client, ticket_id, message, user_id=user_id, markdown=markdown)
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
    markdown: Annotated[
        bool,
        typer.Option("--markdown", "-m", help="Treat message as markdown and convert to HTML"),
    ] = False,
) -> None:
    """Add an internal note to a ticket (not visible to customers)."""
    client = get_client()

    try:
        success = add_note(client, ticket_id, message, user_id=user_id, markdown=markdown)
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


@helpdesk_app.command("chatter")
def helpdesk_chatter(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    limit: Annotated[
        int | None,
        typer.Option(help="Maximum number of messages to show"),
    ] = None,
    show_html: Annotated[
        bool,
        typer.Option("--html", help="Show raw HTML body instead of plain text"),
    ] = False,
) -> None:
    """Show message history/chatter for a ticket."""
    client = get_client()

    try:
        messages = list_messages(client, ticket_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for ticket {ticket_id}[/yellow]")
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
    """Download a single attachment by ID."""
    client = get_client()

    try:
        output_path = download_attachment(client, attachment_id, output)
        console.print(f"[green]Downloaded attachment to {output_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("download-all")
def helpdesk_download_all(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (defaults to current directory)"),
    ] = None,
    extension: Annotated[
        str | None,
        typer.Option("--extension", "--ext", help="Filter by file extension (e.g., pdf, jpg, png)"),
    ] = None,
) -> None:
    """Download all attachments from a ticket."""
    client = get_client()

    try:
        # First check if there are any attachments
        attachments = list_attachments(client, ticket_id)
        if not attachments:
            console.print(f"[yellow]No attachments found for ticket {ticket_id}[/yellow]")
            return

        # Filter by extension if provided
        if extension:
            ext = extension.lower().lstrip(".")
            filtered_attachments = [
                att for att in attachments
                if att.get("name", "").lower().endswith(f".{ext}")
            ]
            if not filtered_attachments:
                console.print(
                    f"[yellow]No {ext} attachments found for ticket {ticket_id}[/yellow]"
                )
                return
            console.print(
                f"[cyan]Downloading {len(filtered_attachments)} .{ext} attachments...[/cyan]"
            )
        else:
            console.print(f"[cyan]Downloading {len(attachments)} attachments...[/cyan]")

        downloaded_files = download_ticket_attachments(
            client, ticket_id, output_dir, extension=extension
        )

        if downloaded_files:
            console.print(
                f"\n[green]Successfully downloaded {len(downloaded_files)} files:[/green]"
            )
            for file_path in downloaded_files:
                console.print(f"  - {file_path}")
        else:
            console.print("[yellow]No files were downloaded[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("fields")
def helpdesk_fields(  # noqa: PLR0912
    ticket_id: Annotated[int | None, typer.Argument(help="Ticket ID (optional)")] = None,
    field_name: Annotated[
        str | None,
        typer.Option(help="Show details for a specific field"),
    ] = None,
) -> None:
    """List available fields or show field values for a specific ticket."""
    client = get_client()

    try:
        if ticket_id:
            # Show fields for a specific ticket
            ticket = get_ticket(client, ticket_id)
            console.print(f"\n[bold cyan]Fields for Ticket #{ticket_id}[/bold cyan]\n")

            if field_name:
                # Show specific field
                if field_name in ticket:
                    console.print(f"[bold]{field_name}:[/bold] {ticket[field_name]}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                # Show all fields
                for key, value in sorted(ticket.items()):
                    console.print(f"[bold]{key}:[/bold] {value}")
        else:
            # List all available fields
            fields = list_ticket_fields(client)
            console.print("\n[bold cyan]Available Helpdesk Ticket Fields[/bold cyan]\n")

            if field_name:
                # Show specific field definition
                if field_name in fields:
                    field_def = fields[field_name]
                    console.print(f"[bold]{field_name}[/bold]")
                    console.print(f"  Type: {field_def.get('type', 'N/A')}")
                    console.print(f"  String: {field_def.get('string', 'N/A')}")
                    console.print(f"  Required: {field_def.get('required', False)}")
                    console.print(f"  Readonly: {field_def.get('readonly', False)}")
                    if field_def.get('help'):
                        console.print(f"  Help: {field_def['help']}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                # List all field names and types
                for name, definition in sorted(fields.items()):
                    field_type = definition.get("type", "unknown")
                    field_label = definition.get("string", name)
                    console.print(f"[cyan]{name}[/cyan] ({field_type}) - {field_label}")

                console.print(f"\n[dim]Total: {len(fields)} fields[/dim]")
                console.print("[dim]Use --field-name to see details for a specific field[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("set")
def helpdesk_set(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    fields: Annotated[
        list[str],
        typer.Argument(help="Field assignments in format 'field=value' or 'field=json:value'"),
    ],
) -> None:
    """Set field values on a ticket.

    Examples:
        odoo-ninja helpdesk set 42 priority=2 name="New Title"
        odoo-ninja helpdesk set 42 user_id=5 stage_id=3
        odoo-ninja helpdesk set 42 'tag_ids=json:[[6,0,[1,2,3]]]'
    """
    client = get_client()

    # Parse field=value pairs
    values: dict[str, Any] = {}

    for field_assignment in fields:
        if "=" not in field_assignment:
            console.print(f"[red]Error:[/red] Invalid format '{field_assignment}'. Use field=value")
            raise typer.Exit(1)

        field, value = field_assignment.split("=", 1)
        field = field.strip()
        value = value.strip()

        # Parse value - try to convert to appropriate type
        parsed_value: Any = value

        # Check for JSON prefix
        if value.startswith("json:"):
            import json
            try:
                parsed_value = json.loads(value[5:])
            except json.JSONDecodeError as e:
                console.print(f"[red]Error:[/red] Invalid JSON for field '{field}': {e}")
                raise typer.Exit(1) from e
        # Try to parse as integer
        elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            parsed_value = int(value)
        # Try to parse as float
        elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
            import contextlib

            with contextlib.suppress(ValueError):
                parsed_value = float(value)
        # Try to parse as boolean
        elif value.lower() in ("true", "false"):
            parsed_value = value.lower() == "true"
        # Keep as string otherwise (remove surrounding quotes if present)
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            parsed_value = value[1:-1]

        values[field] = parsed_value

    try:
        success = set_ticket_fields(client, ticket_id, values)
        if success:
            console.print(
                f"[green]Successfully updated ticket {ticket_id}[/green]"
            )
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to set fields on ticket {ticket_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("attach")
def helpdesk_attach(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    file_path: Annotated[Path, typer.Argument(help="Path to file to attach")],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Custom attachment name (defaults to filename)"),
    ] = None,
) -> None:
    """Attach a file to a ticket."""
    client = get_client()

    try:
        attachment_id = create_attachment(client, ticket_id, file_path, name=name)
        console.print(
            f"[green]Successfully attached {file_path.name} to ticket {ticket_id}[/green]"
        )
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")

        # Show ticket URL for verification
        url = get_ticket_url(client, ticket_id)
        console.print(f"\n[cyan]View ticket:[/cyan] {url}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@helpdesk_app.command("url")
def helpdesk_url(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
) -> None:
    """Get the web URL for a ticket."""
    client = get_client()

    try:
        url = get_ticket_url(client, ticket_id)
        console.print(url)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


# Project task commands


@project_task_app.command("list")
def project_list(
    project: Annotated[str | None, typer.Option(help="Filter by project name")] = None,
    stage: Annotated[str | None, typer.Option(help="Filter by stage name")] = None,
    assigned_to: Annotated[str | None, typer.Option(help="Filter by assigned user name")] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of tasks")] = 50,
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch (can be used multiple times)"),
    ] = None,
) -> None:
    """List project tasks."""
    client = get_client()

    # Build domain filters
    domain: list[Any] = []
    if project:
        domain.append(("project_id.name", "ilike", project))
    if stage:
        domain.append(("stage_id.name", "ilike", stage))
    if assigned_to:
        domain.append(("user_ids.name", "ilike", assigned_to))

    try:
        tasks = list_tasks(client, domain=domain, limit=limit, fields=fields)
        display_tasks(tasks)
        console.print(f"\n[dim]Found {len(tasks)} tasks[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("show")
def project_show(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch (can be used multiple times)"),
    ] = None,
    show_html: Annotated[
        bool,
        typer.Option("--html", help="Show raw HTML description instead of markdown"),
    ] = False,
) -> None:
    """Show detailed task information."""
    client = get_client()

    try:
        task = get_task(client, task_id, fields=fields)

        if fields:
            # If specific fields requested, show them directly
            console.print(f"\n[bold cyan]Task #{task_id}[/bold cyan]\n")
            for key, value in sorted(task.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_task_detail(task, show_html=show_html)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("comment")
def project_comment(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    message: Annotated[str, typer.Argument(help="Comment message")],
    user_id: Annotated[
        int | None, typer.Option(help="User ID to post as (uses default if not set)")
    ] = None,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", "-m", help="Treat message as markdown and convert to HTML"),
    ] = False,
) -> None:
    """Add a comment to a task (visible to followers)."""
    client = get_client()

    # Check if harmful operations are allowed
    if not client.config.allow_harmful_operations:
        console.print(
            "[red]Error:[/red] Posting public comments is disabled. "
            "This is a harmful operation (visible to followers).\n"
            "To enable, set ODOO_ALLOW_HARMFUL_OPERATIONS=true in your .env file.\n"
            "For internal notes (safe), use: [cyan]odoo-ninja project-task note[/cyan]"
        )
        raise typer.Exit(1)

    try:
        success = add_task_comment(client, task_id, message, user_id=user_id, markdown=markdown)
        if success:
            console.print(f"[green]Successfully added comment to task {task_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to task {task_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("note")
def project_note(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    message: Annotated[str, typer.Argument(help="Note message")],
    user_id: Annotated[
        int | None, typer.Option(help="User ID to post as (uses default if not set)")
    ] = None,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", "-m", help="Treat message as markdown and convert to HTML"),
    ] = False,
) -> None:
    """Add an internal note to a task."""
    client = get_client()

    try:
        success = add_task_note(client, task_id, message, user_id=user_id, markdown=markdown)
        if success:
            console.print(f"[green]Successfully added note to task {task_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to task {task_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("tags")
def project_tags() -> None:
    """List available project tags."""
    client = get_client()

    try:
        tags = list_task_tags(client)
        display_task_tags(tags)
        console.print(f"\n[dim]Found {len(tags)} tags[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("tag")
def project_tag(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    tag_id: Annotated[int, typer.Argument(help="Tag ID")],
) -> None:
    """Add a tag to a task."""
    client = get_client()

    try:
        add_tag_to_task(client, task_id, tag_id)
        console.print(f"[green]Successfully added tag {tag_id} to task {task_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("chatter")
def project_chatter(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    limit: Annotated[
        int | None,
        typer.Option(help="Maximum number of messages to show"),
    ] = None,
    show_html: Annotated[
        bool,
        typer.Option("--html", help="Show raw HTML body instead of plain text"),
    ] = False,
) -> None:
    """Show message history/chatter for a task."""
    client = get_client()

    try:
        messages = list_task_messages(client, task_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for task {task_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("attachments")
def project_attachments(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
) -> None:
    """List attachments for a task."""
    client = get_client()

    try:
        attachments = list_task_attachments(client, task_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for task {task_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("download")
def project_download(
    attachment_id: Annotated[int, typer.Argument(help="Attachment ID")],
    output: Annotated[
        Path | None,
        typer.Option(help="Output file path (defaults to attachment name)"),
    ] = None,
) -> None:
    """Download a single attachment by ID."""
    client = get_client()

    try:
        output_path = download_attachment(client, attachment_id, output)
        console.print(f"[green]Downloaded attachment to {output_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("download-all")
def project_download_all(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (defaults to current directory)"),
    ] = None,
    extension: Annotated[
        str | None,
        typer.Option("--extension", "--ext", help="Filter by file extension (e.g., pdf, jpg, png)"),
    ] = None,
) -> None:
    """Download all attachments from a task."""
    client = get_client()

    try:
        # First check if there are any attachments
        attachments = list_task_attachments(client, task_id)
        if not attachments:
            console.print(f"[yellow]No attachments found for task {task_id}[/yellow]")
            return

        # Filter by extension if provided
        if extension:
            ext = extension.lower().lstrip(".")
            filtered_attachments = [
                att for att in attachments if att.get("name", "").lower().endswith(f".{ext}")
            ]
            if not filtered_attachments:
                console.print(f"[yellow]No {ext} attachments found for task {task_id}[/yellow]")
                return
            console.print(
                f"[cyan]Downloading {len(filtered_attachments)} .{ext} attachments...[/cyan]"
            )
        else:
            console.print(f"[cyan]Downloading {len(attachments)} attachments...[/cyan]")

        downloaded_files = download_task_attachments(
            client, task_id, output_dir, extension=extension
        )

        if downloaded_files:
            console.print(
                f"\n[green]Successfully downloaded {len(downloaded_files)} files:[/green]"
            )
            for file_path in downloaded_files:
                console.print(f"  - {file_path}")
        else:
            console.print("[yellow]No files were downloaded[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("fields")
def project_fields(  # noqa: PLR0912
    task_id: Annotated[int | None, typer.Argument(help="Task ID (optional)")] = None,
    field_name: Annotated[
        str | None,
        typer.Option(help="Show details for a specific field"),
    ] = None,
) -> None:
    """List available fields or show field values for a specific task."""
    client = get_client()

    try:
        if task_id:
            # Show fields for a specific task
            task = get_task(client, task_id)
            console.print(f"\n[bold cyan]Fields for Task #{task_id}[/bold cyan]\n")

            if field_name:
                # Show specific field
                if field_name in task:
                    console.print(f"[bold]{field_name}:[/bold] {task[field_name]}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                # Show all fields
                for key, value in sorted(task.items()):
                    console.print(f"[bold]{key}:[/bold] {value}")
        else:
            # List all available fields
            fields = list_task_fields(client)
            console.print("\n[bold cyan]Available Project Task Fields[/bold cyan]\n")

            if field_name:
                # Show specific field definition
                if field_name in fields:
                    field_def = fields[field_name]
                    console.print(f"[bold]{field_name}[/bold]")
                    console.print(f"  Type: {field_def.get('type', 'N/A')}")
                    console.print(f"  String: {field_def.get('string', 'N/A')}")
                    console.print(f"  Required: {field_def.get('required', False)}")
                    console.print(f"  Readonly: {field_def.get('readonly', False)}")
                    if field_def.get("help"):
                        console.print(f"  Help: {field_def['help']}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                # List all field names and types
                for name, definition in sorted(fields.items()):
                    field_type = definition.get("type", "unknown")
                    field_label = definition.get("string", name)
                    console.print(f"[cyan]{name}[/cyan] ({field_type}) - {field_label}")

                console.print(f"\n[dim]Total: {len(fields)} fields[/dim]")
                console.print("[dim]Use --field-name to see details for a specific field[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("set")
def project_set(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    fields: Annotated[
        list[str],
        typer.Argument(help="Field assignments in format 'field=value' or 'field=json:value'"),
    ],
) -> None:
    """Set field values on a task.

    Examples:
        odoo-ninja project-task set 42 priority=1 name="New Task Title"
        odoo-ninja project-task set 42 'user_ids=json:[[6,0,[5]]]' stage_id=3
        odoo-ninja project-task set 42 project_id=10
    """
    client = get_client()

    # Parse field=value pairs
    values: dict[str, Any] = {}

    for field_assignment in fields:
        if "=" not in field_assignment:
            console.print(f"[red]Error:[/red] Invalid format '{field_assignment}'. Use field=value")
            raise typer.Exit(1)

        field, value = field_assignment.split("=", 1)
        field = field.strip()
        value = value.strip()

        # Parse value - try to convert to appropriate type
        parsed_value: Any = value

        # Check for JSON prefix
        if value.startswith("json:"):
            import json

            try:
                parsed_value = json.loads(value[5:])
            except json.JSONDecodeError as e:
                console.print(f"[red]Error:[/red] Invalid JSON for field '{field}': {e}")
                raise typer.Exit(1) from e
        # Try to parse as integer
        elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            parsed_value = int(value)
        # Try to parse as float
        elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
            import contextlib

            with contextlib.suppress(ValueError):
                parsed_value = float(value)
        # Try to parse as boolean
        elif value.lower() in ("true", "false"):
            parsed_value = value.lower() == "true"
        # Keep as string otherwise (remove surrounding quotes if present)
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            parsed_value = value[1:-1]

        values[field] = parsed_value

    try:
        success = set_task_fields(client, task_id, values)
        if success:
            console.print(f"[green]Successfully updated task {task_id}[/green]")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to set fields on task {task_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("attach")
def project_attach(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    file_path: Annotated[Path, typer.Argument(help="Path to file to attach")],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Custom attachment name (defaults to filename)"),
    ] = None,
) -> None:
    """Attach a file to a task."""
    client = get_client()

    try:
        attachment_id = create_task_attachment(client, task_id, file_path, name=name)
        console.print(
            f"[green]Successfully attached {file_path.name} to task {task_id}[/green]"
        )
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")

        # Show task URL for verification
        url = get_task_url(client, task_id)
        console.print(f"\n[cyan]View task:[/cyan] {url}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("url")
def project_url(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
) -> None:
    """Get the web URL for a task."""
    client = get_client()

    try:
        url = get_task_url(client, task_id)
        console.print(url)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


# Project (project.project) commands


@project_project_app.command("list")
def project_project_list(
    name: Annotated[str | None, typer.Option(help="Filter by project name")] = None,
    user: Annotated[str | None, typer.Option(help="Filter by project manager name")] = None,
    partner: Annotated[str | None, typer.Option(help="Filter by partner name")] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of projects")] = 50,
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch (can be used multiple times)"),
    ] = None,
) -> None:
    """List projects."""
    client = get_client()

    # Build domain filters
    domain: list[Any] = []
    if name:
        domain.append(("name", "ilike", name))
    if user:
        domain.append(("user_id.name", "ilike", user))
    if partner:
        domain.append(("partner_id.name", "ilike", partner))

    try:
        projects = list_projects(client, domain=domain, limit=limit, fields=fields)
        display_projects(projects)
        console.print(f"\n[dim]Found {len(projects)} projects[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("show")
def project_project_show(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch (can be used multiple times)"),
    ] = None,
    show_html: Annotated[
        bool,
        typer.Option("--html", help="Show raw HTML description instead of markdown"),
    ] = False,
) -> None:
    """Show detailed project information."""
    client = get_client()

    try:
        project = get_project(client, project_id, fields=fields)

        if fields:
            # If specific fields requested, show them directly
            console.print(f"\n[bold cyan]Project #{project_id}[/bold cyan]\n")
            for key, value in sorted(project.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_project_detail(project, show_html=show_html)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("comment")
def project_project_comment(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
    message: Annotated[str, typer.Argument(help="Comment message")],
    user_id: Annotated[
        int | None, typer.Option(help="User ID to post as (uses default if not set)")
    ] = None,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", "-m", help="Treat message as markdown and convert to HTML"),
    ] = False,
) -> None:
    """Add a comment to a project (visible to followers)."""
    client = get_client()

    # Check if harmful operations are allowed
    if not client.config.allow_harmful_operations:
        console.print(
            "[red]Error:[/red] Posting public comments is disabled. "
            "This is a harmful operation (visible to followers).\n"
            "To enable, set ODOO_ALLOW_HARMFUL_OPERATIONS=true in your .env file.\n"
            "For internal notes (safe), use: [cyan]odoo-ninja project note[/cyan]"
        )
        raise typer.Exit(1)

    try:
        success = add_project_comment(
            client, project_id, message, user_id=user_id, markdown=markdown
        )
        if success:
            console.print(f"[green]Successfully added comment to project {project_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to project {project_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("note")
def project_project_note(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
    message: Annotated[str, typer.Argument(help="Note message")],
    user_id: Annotated[
        int | None, typer.Option(help="User ID to post as (uses default if not set)")
    ] = None,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", "-m", help="Treat message as markdown and convert to HTML"),
    ] = False,
) -> None:
    """Add an internal note to a project."""
    client = get_client()

    try:
        success = add_project_note(client, project_id, message, user_id=user_id, markdown=markdown)
        if success:
            console.print(f"[green]Successfully added note to project {project_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to project {project_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("chatter")
def project_project_chatter(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
    limit: Annotated[
        int | None,
        typer.Option(help="Maximum number of messages to show"),
    ] = None,
    show_html: Annotated[
        bool,
        typer.Option("--html", help="Show raw HTML body instead of plain text"),
    ] = False,
) -> None:
    """Show message history/chatter for a project."""
    client = get_client()

    try:
        messages = list_project_messages(client, project_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for project {project_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("attachments")
def project_project_attachments(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
) -> None:
    """List attachments for a project."""
    client = get_client()

    try:
        attachments = list_project_attachments(client, project_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for project {project_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("fields")
def project_project_fields(  # noqa: PLR0912
    project_id: Annotated[int | None, typer.Argument(help="Project ID (optional)")] = None,
    field_name: Annotated[
        str | None,
        typer.Option(help="Show details for a specific field"),
    ] = None,
) -> None:
    """List available fields or show field values for a specific project."""
    client = get_client()

    try:
        if project_id:
            # Show fields for a specific project
            project = get_project(client, project_id)
            console.print(f"\n[bold cyan]Fields for Project #{project_id}[/bold cyan]\n")

            if field_name:
                # Show specific field
                if field_name in project:
                    console.print(f"[bold]{field_name}:[/bold] {project[field_name]}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                # Show all fields
                for key, value in sorted(project.items()):
                    console.print(f"[bold]{key}:[/bold] {value}")
        else:
            # List all available fields
            fields = list_project_fields(client)
            console.print("\n[bold cyan]Available Project Fields[/bold cyan]\n")

            if field_name:
                # Show specific field definition
                if field_name in fields:
                    field_def = fields[field_name]
                    console.print(f"[bold]{field_name}[/bold]")
                    console.print(f"  Type: {field_def.get('type', 'N/A')}")
                    console.print(f"  String: {field_def.get('string', 'N/A')}")
                    console.print(f"  Required: {field_def.get('required', False)}")
                    console.print(f"  Readonly: {field_def.get('readonly', False)}")
                    if field_def.get("help"):
                        console.print(f"  Help: {field_def['help']}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                # List all field names and types
                for name, definition in sorted(fields.items()):
                    field_type = definition.get("type", "unknown")
                    field_label = definition.get("string", name)
                    console.print(f"[cyan]{name}[/cyan] ({field_type}) - {field_label}")

                console.print(f"\n[dim]Total: {len(fields)} fields[/dim]")
                console.print("[dim]Use --field-name to see details for a specific field[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("set")
def project_project_set(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
    fields: Annotated[
        list[str],
        typer.Argument(help="Field assignments in format 'field=value' or 'field=json:value'"),
    ],
) -> None:
    """Set field values on a project.

    Examples:
        odoo-ninja project set 42 name="New Project Name"
        odoo-ninja project set 42 user_id=5
    """
    client = get_client()

    # Parse field=value pairs
    values: dict[str, Any] = {}

    for field_assignment in fields:
        if "=" not in field_assignment:
            console.print(f"[red]Error:[/red] Invalid format '{field_assignment}'. Use field=value")
            raise typer.Exit(1)

        field, value = field_assignment.split("=", 1)
        field = field.strip()
        value = value.strip()

        # Parse value - try to convert to appropriate type
        parsed_value: Any = value

        # Check for JSON prefix
        if value.startswith("json:"):
            import json

            try:
                parsed_value = json.loads(value[5:])
            except json.JSONDecodeError as e:
                console.print(f"[red]Error:[/red] Invalid JSON for field '{field}': {e}")
                raise typer.Exit(1) from e
        # Try to parse as integer
        elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            parsed_value = int(value)
        # Try to parse as float
        elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
            import contextlib

            with contextlib.suppress(ValueError):
                parsed_value = float(value)
        # Try to parse as boolean
        elif value.lower() in ("true", "false"):
            parsed_value = value.lower() == "true"
        # Keep as string otherwise (remove surrounding quotes if present)
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            parsed_value = value[1:-1]

        values[field] = parsed_value

    try:
        success = set_project_fields(client, project_id, values)
        if success:
            console.print(f"[green]Successfully updated project {project_id}[/green]")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to set fields on project {project_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("attach")
def project_project_attach(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
    file_path: Annotated[Path, typer.Argument(help="Path to file to attach")],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Custom attachment name (defaults to filename)"),
    ] = None,
) -> None:
    """Attach a file to a project."""
    client = get_client()

    try:
        attachment_id = create_project_attachment(client, project_id, file_path, name=name)
        console.print(
            f"[green]Successfully attached {file_path.name} to project {project_id}[/green]"
        )
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")

        # Show project URL for verification
        url = get_project_url(client, project_id)
        console.print(f"\n[cyan]View project:[/cyan] {url}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_project_app.command("url")
def project_project_url(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
) -> None:
    """Get the web URL for a project."""
    client = get_client()

    try:
        url = get_project_url(client, project_id)
        console.print(url)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
