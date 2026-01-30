"""Main CLI application for Vodoo."""

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from vodoo.base import (
    display_attachments,
    display_messages,
    display_records,
    download_attachment,
    get_record,
    parse_field_assignment,
)
from vodoo.client import OdooClient
from vodoo.config import get_config
from vodoo.crm import (
    add_comment as add_lead_comment,
)
from vodoo.crm import (
    add_note as add_lead_note,
)
from vodoo.crm import (
    add_tag_to_lead,
    create_lead_attachment,
    display_lead_detail,
    display_leads,
    download_lead_attachments,
    get_lead,
    get_lead_url,
    list_lead_attachments,
    list_lead_fields,
    list_lead_messages,
    list_leads,
    set_lead_fields,
)
from vodoo.crm import (
    display_tags as display_lead_tags,
)
from vodoo.crm import (
    list_tags as list_lead_tags,
)
from vodoo.generic import (
    call_method,
    create_record,
    delete_record,
    search_records,
    update_record,
)
from vodoo.helpdesk import (
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
from vodoo.knowledge import (
    add_comment as add_article_comment,
)
from vodoo.knowledge import (
    add_note as add_article_note,
)
from vodoo.knowledge import (
    display_article_detail,
    display_articles,
    get_article,
    get_article_url,
    list_article_attachments,
    list_article_messages,
    list_articles,
)
from vodoo.project import (
    add_comment as add_task_comment,
)
from vodoo.project import (
    add_note as add_task_note,
)
from vodoo.project import (
    add_tag_to_task,
    create_task,
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
from vodoo.project import (
    create_tag as create_project_tag,
)
from vodoo.project import (
    delete_tag as delete_project_tag,
)
from vodoo.project_project import (
    add_comment as add_project_comment,
)
from vodoo.project_project import (
    add_note as add_project_note,
)
from vodoo.project_project import (
    create_project_attachment,
    display_project_detail,
    display_projects,
    display_stages,
    get_project,
    get_project_url,
    list_project_attachments,
    list_project_fields,
    list_project_messages,
    list_projects,
    list_stages,
    set_project_fields,
)

app = typer.Typer(
    name="vodoo",
    help="CLI tool for Odoo: helpdesk, projects, tasks, and CRM",
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

knowledge_app = typer.Typer(
    name="knowledge",
    help="Knowledge article operations",
    no_args_is_help=True,
)
app.add_typer(knowledge_app, name="knowledge")

model_app = typer.Typer(
    name="model",
    help="Generic model operations (create, read, update, delete)",
    no_args_is_help=True,
)
app.add_typer(model_app, name="model")

crm_app = typer.Typer(
    name="crm",
    help="CRM lead/opportunity operations",
    no_args_is_help=True,
)
app.add_typer(crm_app, name="crm")

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


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        from importlib.metadata import version

        app_version = version("vodoo")
        console.print(f"vodoo version {app_version}")
        raise typer.Exit()


@app.callback()
def main_callback(
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable colored output for programmatic use"),
    ] = False,
    version: Annotated[  # noqa: ARG001
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Global options for vodoo CLI."""
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
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion"),
    ] = False,
) -> None:
    """Add a comment to a ticket (visible to customers)."""
    client = get_client()

    try:
        success = add_comment(
            client, ticket_id, message, user_id=author_id, markdown=not no_markdown
        )
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
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion"),
    ] = False,
) -> None:
    """Add an internal note to a ticket (not visible to customers)."""
    client = get_client()

    try:
        success = add_note(client, ticket_id, message, user_id=author_id, markdown=not no_markdown)
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
                att for att in attachments if att.get("name", "").lower().endswith(f".{ext}")
            ]
            if not filtered_attachments:
                console.print(f"[yellow]No {ext} attachments found for ticket {ticket_id}[/yellow]")
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


@helpdesk_app.command("set")
def helpdesk_set(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    fields: Annotated[
        list[str],
        typer.Argument(help="Field assignments in format 'field=value' or 'field+=amount'"),
    ],
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion for HTML fields"),
    ] = False,
) -> None:
    """Set field values on a ticket.

    Supports operators: =, +=, -=, *=, /=
    HTML fields (like description) automatically convert markdown to HTML.

    Examples:
        vodoo helpdesk set 42 priority=2 name="New Title"
        vodoo helpdesk set 42 user_id=5 stage_id=3
        vodoo helpdesk set 42 priority+=1
        vodoo helpdesk set 42 'tag_ids=json:[[6,0,[1,2,3]]]'
        vodoo helpdesk set 42 'description=# Heading\n\nParagraph text'
    """
    client = get_client()

    # Parse field assignments
    values: dict[str, Any] = {}

    try:
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, "helpdesk.ticket", ticket_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    try:
        success = set_ticket_fields(client, ticket_id, values)
        if success:
            console.print(f"[green]Successfully updated ticket {ticket_id}[/green]")
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


@project_task_app.command("create")
def project_task_create(
    name: Annotated[str, typer.Argument(help="Task name")],
    project_id: Annotated[int, typer.Option("--project", "-p", help="Project ID (required)")],
    description: Annotated[
        str | None, typer.Option("--desc", "-d", help="Task description")
    ] = None,
    user_id: Annotated[
        list[int] | None, typer.Option("--user", "-u", help="Assigned user ID (can repeat)")
    ] = None,
    tag_id: Annotated[
        list[int] | None, typer.Option("--tag", "-t", help="Tag ID (can repeat)")
    ] = None,
    parent_id: Annotated[
        int | None, typer.Option("--parent", help="Parent task ID for subtask")
    ] = None,
) -> None:
    """Create a new project task.

    Examples:
        vodoo project-task create "Fix login bug" --project 10
        vodoo project-task create "Review PR" -p 10 --user 5 --tag 1 --tag 2
        vodoo project-task create "Subtask" -p 10 --parent 42
    """
    client = get_client()

    try:
        task_id = create_task(
            client,
            name=name,
            project_id=project_id,
            description=description,
            user_ids=user_id,
            tag_ids=tag_id,
            parent_id=parent_id,
        )
        console.print(f"[green]Successfully created task '{name}' with ID {task_id}[/green]")

        # Show the URL
        url = get_task_url(client, task_id)
        console.print(f"\n[cyan]View task:[/cyan] {url}")
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
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion"),
    ] = False,
) -> None:
    """Add a comment to a task (visible to followers)."""
    client = get_client()

    try:
        success = add_task_comment(
            client, task_id, message, user_id=author_id, markdown=not no_markdown
        )
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
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion"),
    ] = False,
) -> None:
    """Add an internal note to a task."""
    client = get_client()

    try:
        success = add_task_note(
            client, task_id, message, user_id=author_id, markdown=not no_markdown
        )
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


@project_task_app.command("tag-create")
def project_tag_create(
    name: Annotated[str, typer.Argument(help="Tag name")],
    color: Annotated[int | None, typer.Option(help="Tag color index (0-11)")] = None,
) -> None:
    """Create a new project tag."""
    client = get_client()

    try:
        tag_id = create_project_tag(client, name, color=color)
        console.print(f"[green]Successfully created tag '{name}' with ID {tag_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@project_task_app.command("tag-delete")
def project_tag_delete(
    tag_id: Annotated[int, typer.Argument(help="Tag ID to delete")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Confirm deletion")] = False,
) -> None:
    """Delete a project tag."""
    client = get_client()

    if not confirm:
        console.print("[red]Error:[/red] Deletion requires --confirm flag")
        console.print("[yellow]Use: vodoo project-task tag-delete <id> --confirm[/yellow]")
        raise typer.Exit(1)

    try:
        success = delete_project_tag(client, tag_id)
        if success:
            console.print(f"[green]Successfully deleted tag {tag_id}[/green]")
        else:
            console.print(f"[red]Failed to delete tag {tag_id}[/red]")
            raise typer.Exit(1)
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
        typer.Argument(help="Field assignments in format 'field=value' or 'field+=amount'"),
    ],
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion for HTML fields"),
    ] = False,
) -> None:
    """Set field values on a task.

    Supports operators: =, +=, -=, *=, /=
    HTML fields (like description) automatically convert markdown to HTML.

    Examples:
        vodoo project-task set 42 priority=1 name="New Task Title"
        vodoo project-task set 42 'user_ids=json:[[6,0,[5]]]' stage_id=3
        vodoo project-task set 42 project_id=10
        vodoo project-task set 42 priority+=1
        vodoo project-task set 42 'description=# Task Details\n\n- Item 1\n- Item 2'
    """
    client = get_client()

    # Parse field assignments
    values: dict[str, Any] = {}

    try:
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, "project.task", task_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

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
        console.print(f"[green]Successfully attached {file_path.name} to task {task_id}[/green]")
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
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion"),
    ] = False,
) -> None:
    """Add a comment to a project (visible to followers)."""
    client = get_client()

    try:
        success = add_project_comment(
            client, project_id, message, user_id=author_id, markdown=not no_markdown
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
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion"),
    ] = False,
) -> None:
    """Add an internal note to a project."""
    client = get_client()

    try:
        success = add_project_note(
            client, project_id, message, user_id=author_id, markdown=not no_markdown
        )
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
        typer.Argument(help="Field assignments in format 'field=value' or 'field+=amount'"),
    ],
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion for HTML fields"),
    ] = False,
) -> None:
    """Set field values on a project.

    Supports operators: =, +=, -=, *=, /=
    HTML fields automatically convert markdown to HTML.

    Examples:
        vodoo project set 42 name="New Project Name"
        vodoo project set 42 user_id=5
    """
    client = get_client()

    # Parse field assignments
    values: dict[str, Any] = {}

    try:
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, "project.project", project_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

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


@project_project_app.command("stages")
def project_project_stages(
    project_id: Annotated[
        int | None,
        typer.Option("--project", "-p", help="Filter stages by project ID"),
    ] = None,
) -> None:
    """List task stages for projects.

    Shows all stages or only stages available for a specific project.

    Examples:
        vodoo project stages              # All stages
        vodoo project stages --project 10 # Stages for project ID 10
    """
    client = get_client()

    try:
        stages = list_stages(client, project_id=project_id)
        if stages:
            display_stages(stages)
            console.print(f"\n[dim]Found {len(stages)} stages[/dim]")
        elif project_id:
            console.print(f"[yellow]No stages found for project {project_id}[/yellow]")
        else:
            console.print("[yellow]No stages found[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


# Knowledge commands


@knowledge_app.command("list")
def knowledge_list(
    name: Annotated[str | None, typer.Option(help="Filter by article name")] = None,
    parent: Annotated[str | None, typer.Option(help="Filter by parent article name")] = None,
    category: Annotated[
        str | None, typer.Option(help="Filter by category (workspace, private, shared)")
    ] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of articles")] = 50,
) -> None:
    """List knowledge articles."""
    client = get_client()

    domain: list[Any] = []
    if name:
        domain.append(("name", "ilike", name))
    if parent:
        domain.append(("parent_id.name", "ilike", parent))
    if category:
        domain.append(("category", "=", category))

    try:
        articles = list_articles(client, domain=domain, limit=limit)
        display_articles(articles)
        console.print(f"\n[dim]Found {len(articles)} articles[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@knowledge_app.command("show")
def knowledge_show(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
    show_html: Annotated[
        bool, typer.Option("--html", help="Show raw HTML content instead of markdown")
    ] = False,
) -> None:
    """Show detailed article information."""
    client = get_client()

    try:
        article = get_article(client, article_id)
        display_article_detail(article, show_html=show_html)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@knowledge_app.command("comment")
def knowledge_comment(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
    message: Annotated[str, typer.Argument(help="Comment message")],
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool, typer.Option("--no-markdown", help="Disable markdown to HTML conversion")
    ] = False,
) -> None:
    """Add a comment to an article (visible to followers)."""
    client = get_client()

    try:
        success = add_article_comment(
            client, article_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added comment to article {article_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to article {article_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@knowledge_app.command("note")
def knowledge_note(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
    message: Annotated[str, typer.Argument(help="Note message")],
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool, typer.Option("--no-markdown", help="Disable markdown to HTML conversion")
    ] = False,
) -> None:
    """Add an internal note to an article."""
    client = get_client()

    try:
        success = add_article_note(
            client, article_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added note to article {article_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to article {article_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@knowledge_app.command("chatter")
def knowledge_chatter(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
    limit: Annotated[int | None, typer.Option(help="Maximum number of messages")] = None,
    show_html: Annotated[
        bool, typer.Option("--html", help="Show raw HTML body instead of plain text")
    ] = False,
) -> None:
    """Show message history/chatter for an article."""
    client = get_client()

    try:
        messages = list_article_messages(client, article_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for article {article_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@knowledge_app.command("attachments")
def knowledge_attachments(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
) -> None:
    """List attachments for an article."""
    client = get_client()

    try:
        attachments = list_article_attachments(client, article_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for article {article_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@knowledge_app.command("url")
def knowledge_url(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
) -> None:
    """Get the web URL for an article."""
    client = get_client()

    try:
        url = get_article_url(client, article_id)
        console.print(url)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


# Generic model commands


@model_app.command("create")
def model_create(
    model: Annotated[str, typer.Argument(help="Model name (e.g., semadox.template.registry)")],
    fields: Annotated[
        list[str],
        typer.Argument(help="Field assignments in format 'field=value'"),
    ],
) -> None:
    """Create a new record in any model.

    Examples:
        vodoo model create semadox.template.registry name=my_template category=invoice

        vodoo model create res.partner name="John Doe" email=john@example.com

        vodoo model create project.task name="New Task" project_id=10
    """
    client = get_client()

    # Parse field assignments
    values: dict[str, Any] = {}
    try:
        for field_assignment in fields:
            # Parse using existing helper
            field, value = parse_field_assignment(client, model, 0, field_assignment)
            values[field] = value
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    try:
        record_id = create_record(client, model, values)
        console.print(f"[green]Successfully created record with ID {record_id}[/green]")
        console.print(f"Model: {model}")
        for field, value in values.items():
            console.print(f"  {field} = {value}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@model_app.command("read")
def model_read(
    model: Annotated[str, typer.Argument(help="Model name")],
    record_id: Annotated[int | None, typer.Argument(help="Record ID (optional)")] = None,
    domain: Annotated[
        str | None,
        typer.Option(help="Search domain as JSON string"),
    ] = None,
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Fields to fetch"),
    ] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of records")] = 50,
) -> None:
    """Read record(s) from any model.

    Examples:
        # Read specific record
        vodoo model read semadox.template.registry 42

        # Search records
        vodoo model read semadox.template.registry --domain='[["category","=","invoice"]]'

        # With specific fields
        vodoo model read res.partner --field name --field email --limit 10
    """
    client = get_client()

    try:
        if record_id:
            # Read specific record
            record = get_record(client, model, record_id, fields=fields)
            console.print(f"\n[bold cyan]Record #{record_id} from {model}[/bold cyan]\n")
            for key, value in sorted(record.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            # Search records
            import json

            parsed_domain = json.loads(domain) if domain else []

            records = search_records(
                client,
                model,
                domain=parsed_domain,
                fields=fields,
                limit=limit,
            )

            if records:
                display_records(records, title=f"{model} Records")
                console.print(f"\n[dim]Found {len(records)} records[/dim]")
            else:
                console.print("[yellow]No records found[/yellow]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@model_app.command("update")
def model_update(
    model: Annotated[str, typer.Argument(help="Model name")],
    record_id: Annotated[int, typer.Argument(help="Record ID")],
    fields: Annotated[
        list[str],
        typer.Argument(help="Field assignments in format 'field=value'"),
    ],
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion for HTML fields"),
    ] = False,
) -> None:
    """Update a record in any model.

    HTML fields automatically convert markdown to HTML.

    Examples:
        vodoo model update semadox.template.registry 42 version=2.0.0 active=true

        vodoo model update res.partner 123 name="Jane Doe" phone="+1234567890"
    """
    client = get_client()

    # Parse field assignments
    values: dict[str, Any] = {}
    try:
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, model, record_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    try:
        success = update_record(client, model, record_id, values)
        if success:
            console.print(f"[green]Successfully updated record {record_id}[/green]")
            console.print(f"Model: {model}")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to update record {record_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@model_app.command("delete")
def model_delete(
    model: Annotated[str, typer.Argument(help="Model name")],
    record_id: Annotated[int, typer.Argument(help="Record ID")],
) -> None:
    """Delete a record from any model.

    Examples:
        vodoo model delete semadox.template.registry 42
    """
    client = get_client()

    try:
        success = delete_record(client, model, record_id)
        if success:
            console.print(f"[green]Successfully deleted record {record_id} from {model}[/green]")
        else:
            console.print(f"[red]Failed to delete record {record_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@model_app.command("call")
def model_call(
    model: Annotated[str, typer.Argument(help="Model name")],
    method: Annotated[str, typer.Argument(help="Method to call")],
    args_json: Annotated[str, typer.Option("--args", help="JSON array of arguments")] = "[]",
    kwargs_json: Annotated[str, typer.Option("--kwargs", help="JSON object of kwargs")] = "{}",
) -> None:
    """Call a method on a model.

    Examples:
        vodoo model call res.partner name_search --args '["John"]'
        vodoo model call res.partner search --kwargs '{"domain": [["name", "ilike", "acme"]]}'
    """
    client = get_client()
    import json

    try:
        args = json.loads(args_json)
        kwargs = json.loads(kwargs_json)

        result = call_method(
            client,
            model,
            method,
            args=args,
            kwargs=kwargs,
        )

        console.print("[green]Method executed successfully[/green]")
        console.print(f"Result: {result}")
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Error executing method: {e}[/red]")
        raise typer.Exit(1) from e


# CRM commands


@crm_app.command("list")
def crm_list(
    search: Annotated[
        str | None,
        typer.Option("--search", "-s", help="Search in name, email, phone, description"),
    ] = None,
    stage: Annotated[str | None, typer.Option(help="Filter by stage name")] = None,
    team: Annotated[str | None, typer.Option(help="Filter by sales team name")] = None,
    user: Annotated[str | None, typer.Option(help="Filter by salesperson name")] = None,
    partner: Annotated[str | None, typer.Option(help="Filter by partner/customer name")] = None,
    lead_type: Annotated[
        str | None,
        typer.Option("--type", help="Filter by type: 'lead' or 'opportunity'"),
    ] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of leads")] = 50,
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch"),
    ] = None,
) -> None:
    """List CRM leads/opportunities."""
    client = get_client()

    domain: list[Any] = []

    # Text search across multiple fields using OR domain
    if search:
        search_fields = ["name", "email_from", "phone", "contact_name", "description"]
        # Build OR domain: ['|', '|', '|', '|', (f1, ilike, x), (f2, ilike, x), ...]
        # Need n-1 OR operators for n conditions
        for _ in range(len(search_fields) - 1):
            domain.append("|")
        for field in search_fields:
            domain.append((field, "ilike", search))

    if stage:
        domain.append(("stage_id.name", "ilike", stage))
    if team:
        domain.append(("team_id.name", "ilike", team))
    if user:
        domain.append(("user_id.name", "ilike", user))
    if partner:
        domain.append(("partner_id.name", "ilike", partner))
    if lead_type:
        domain.append(("type", "=", lead_type))

    try:
        leads = list_leads(client, domain=domain, limit=limit, fields=fields)
        display_leads(leads)
        console.print(f"\n[dim]Found {len(leads)} leads/opportunities[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("show")
def crm_show(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Specific fields to fetch"),
    ] = None,
    show_html: Annotated[
        bool,
        typer.Option("--html", help="Show raw HTML description"),
    ] = False,
) -> None:
    """Show detailed lead/opportunity information."""
    client = get_client()

    try:
        lead = get_lead(client, lead_id, fields=fields)
        if fields:
            console.print(f"\n[bold cyan]Lead #{lead_id}[/bold cyan]\n")
            for key, value in sorted(lead.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_lead_detail(lead, show_html=show_html)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("comment")
def crm_comment(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    message: Annotated[str, typer.Argument(help="Comment message")],
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool, typer.Option("--no-markdown", help="Disable markdown conversion")
    ] = False,
) -> None:
    """Add a comment to a lead (visible to followers)."""
    client = get_client()

    try:
        success = add_lead_comment(
            client, lead_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added comment to lead {lead_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to lead {lead_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("note")
def crm_note(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    message: Annotated[str, typer.Argument(help="Note message")],
    author_id: Annotated[
        int | None, typer.Option("--author", "-a", help="User ID to post as")
    ] = None,
    no_markdown: Annotated[
        bool, typer.Option("--no-markdown", help="Disable markdown conversion")
    ] = False,
) -> None:
    """Add an internal note to a lead (not visible to followers)."""
    client = get_client()

    try:
        success = add_lead_note(
            client, lead_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added note to lead {lead_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to lead {lead_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("tags")
def crm_tags() -> None:
    """List available CRM tags."""
    client = get_client()

    try:
        tags = list_lead_tags(client)
        display_lead_tags(tags)
        console.print(f"\n[dim]Found {len(tags)} tags[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("tag")
def crm_tag(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    tag_id: Annotated[int, typer.Argument(help="Tag ID")],
) -> None:
    """Add a tag to a lead."""
    client = get_client()

    try:
        add_tag_to_lead(client, lead_id, tag_id)
        console.print(f"[green]Successfully added tag {tag_id} to lead {lead_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("chatter")
def crm_chatter(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    limit: Annotated[int | None, typer.Option(help="Max messages to show")] = None,
    show_html: Annotated[bool, typer.Option("--html", help="Show raw HTML")] = False,
) -> None:
    """Show message history/chatter for a lead."""
    client = get_client()

    try:
        messages = list_lead_messages(client, lead_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for lead {lead_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("attachments")
def crm_attachments(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
) -> None:
    """List attachments for a lead."""
    client = get_client()

    try:
        attachments = list_lead_attachments(client, lead_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for lead {lead_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("download")
def crm_download(
    attachment_id: Annotated[int, typer.Argument(help="Attachment ID")],
    output: Annotated[Path | None, typer.Option(help="Output file path")] = None,
) -> None:
    """Download a single attachment by ID."""
    client = get_client()

    try:
        output_path = download_attachment(client, attachment_id, output)
        console.print(f"[green]Downloaded attachment to {output_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("download-all")
def crm_download_all(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    output_dir: Annotated[Path | None, typer.Option("--output", "-o", help="Output dir")] = None,
    extension: Annotated[str | None, typer.Option("--ext", help="Filter by extension")] = None,
) -> None:
    """Download all attachments from a lead."""
    client = get_client()

    try:
        attachments = list_lead_attachments(client, lead_id)
        if not attachments:
            console.print(f"[yellow]No attachments found for lead {lead_id}[/yellow]")
            return

        if extension:
            ext = extension.lower().lstrip(".")
            attachments = [a for a in attachments if a.get("name", "").lower().endswith(f".{ext}")]
            if not attachments:
                console.print(f"[yellow]No {ext} attachments found for lead {lead_id}[/yellow]")
                return

        console.print(f"[cyan]Downloading {len(attachments)} attachments...[/cyan]")
        downloaded = download_lead_attachments(client, lead_id, output_dir, extension=extension)

        if downloaded:
            console.print(f"\n[green]Downloaded {len(downloaded)} files:[/green]")
            for f in downloaded:
                console.print(f"  - {f}")
        else:
            console.print("[yellow]No files were downloaded[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("fields")
def crm_fields(
    lead_id: Annotated[int | None, typer.Argument(help="Lead ID (optional)")] = None,
    field_name: Annotated[str | None, typer.Option(help="Show specific field")] = None,
) -> None:
    """List available fields or show field values for a specific lead."""
    client = get_client()

    try:
        if lead_id:
            lead = get_lead(client, lead_id)
            console.print(f"\n[bold cyan]Fields for Lead #{lead_id}[/bold cyan]\n")
            if field_name:
                if field_name in lead:
                    console.print(f"[bold]{field_name}:[/bold] {lead[field_name]}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                for key, value in sorted(lead.items()):
                    console.print(f"[bold]{key}:[/bold] {value}")
        else:
            fields = list_lead_fields(client)
            console.print("\n[bold cyan]Available CRM Lead Fields[/bold cyan]\n")
            if field_name:
                if field_name in fields:
                    fd = fields[field_name]
                    console.print(f"[bold]{field_name}[/bold]")
                    console.print(f"  Type: {fd.get('type', 'N/A')}")
                    console.print(f"  String: {fd.get('string', 'N/A')}")
                    console.print(f"  Required: {fd.get('required', False)}")
                    console.print(f"  Readonly: {fd.get('readonly', False)}")
                else:
                    console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
            else:
                for name, defn in sorted(fields.items()):
                    console.print(
                        f"[cyan]{name}[/cyan] ({defn.get('type')}) - {defn.get('string')}"
                    )
                console.print(f"\n[dim]Total: {len(fields)} fields[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("set")
def crm_set(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    fields: Annotated[list[str], typer.Argument(help="Field assignments (field=value)")],
    no_markdown: Annotated[
        bool,
        typer.Option("--no-markdown", help="Disable markdown to HTML conversion for HTML fields"),
    ] = False,
) -> None:
    """Set field values on a lead.

    HTML fields automatically convert markdown to HTML.
    """
    client = get_client()

    values: dict[str, Any] = {}
    try:
        for fa in fields:
            field, value = parse_field_assignment(
                client, "crm.lead", lead_id, fa, no_markdown=no_markdown
            )
            values[field] = value
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    try:
        success = set_lead_fields(client, lead_id, values)
        if success:
            console.print(f"[green]Successfully updated lead {lead_id}[/green]")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to update lead {lead_id}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("attach")
def crm_attach(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    file_path: Annotated[Path, typer.Argument(help="Path to file to attach")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Custom name")] = None,
) -> None:
    """Attach a file to a lead."""
    client = get_client()

    try:
        attachment_id = create_lead_attachment(client, lead_id, file_path, name=name)
        console.print(f"[green]Successfully attached {file_path.name} to lead {lead_id}[/green]")
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")
        url = get_lead_url(client, lead_id)
        console.print(f"\n[cyan]View lead:[/cyan] {url}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@crm_app.command("url")
def crm_url(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
) -> None:
    """Get the web URL for a lead."""
    client = get_client()

    try:
        url = get_lead_url(client, lead_id)
        console.print(url)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
