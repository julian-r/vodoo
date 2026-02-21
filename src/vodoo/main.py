"""Main CLI application for Vodoo."""

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
from rich.console import Console
from rich.table import Table

from vodoo.base import (
    configure_output,
    display_attachments,
    display_messages,
    display_record_detail,
    display_records,
    display_tags,
    download_attachment,
    get_record,
)
from vodoo.client import OdooClient
from vodoo.config import (
    detect_config_file,
    get_config,
    list_instance_profiles,
    read_default_instance,
    resolve_instance,
    write_default_instance,
)
from vodoo.exceptions import (
    AuthenticationError,
    OdooAccessDeniedError,
    OdooAccessError,
    RecordNotFoundError,
    TransportError,
    VodooError,
)
from vodoo.fields import parse_field_assignment
from vodoo.knowledge import display_article_detail
from vodoo.projects import display_stages
from vodoo.security import (
    GROUP_DEFINITIONS,
)


@contextmanager
def _handle_errors() -> Any:
    """Catch Vodoo/Odoo exceptions and exit with a formatted error message."""
    try:
        yield
    except RecordNotFoundError as e:
        console.print(f"[red]Not found:[/red] {e}")
        raise typer.Exit(1) from e
    except (OdooAccessError, OdooAccessDeniedError) as e:
        console.print(f"[red]Access denied:[/red] {e}")
        raise typer.Exit(1) from e
    except AuthenticationError as e:
        console.print(f"[red]Authentication failed:[/red] {e}")
        raise typer.Exit(1) from e
    except TransportError as e:
        console.print(f"[red]Server error:[/red] {e}")
        raise typer.Exit(1) from e
    except VodooError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(1) from e


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

security_app = typer.Typer(
    name="security",
    help="Security group utilities",
    no_args_is_help=True,
)
app.add_typer(security_app, name="security")

timer_app = typer.Typer(
    name="timer",
    help="Timer / timesheet operations (start, stop, status)",
    no_args_is_help=True,
)
app.add_typer(timer_app, name="timer")

config_app = typer.Typer(
    name="config",
    help="Configuration and instance profile utilities",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")

# Global state for CLI runtime configuration
_console_config: dict[str, bool] = {"simple": False}
_instance_config: dict[str, str | None] = {"name": None}

console = Console()


def get_console() -> Console:
    """Get console instance with current configuration.

    Returns:
        Console instance

    """
    simple = _console_config["simple"]
    return Console(force_terminal=not simple, no_color=simple)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        from importlib.metadata import version

        app_version = version("vodoo")
        console.print(f"vodoo version {app_version}")
        raise typer.Exit()


@app.callback()
def main_callback(
    simple: Annotated[
        bool,
        typer.Option("--simple", help="Plain TSV output instead of rich tables"),
    ] = False,
    instance: Annotated[
        str | None,
        typer.Option("--instance", "-i", help="Instance/profile name to use"),
    ] = None,
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
    _console_config["simple"] = simple
    _instance_config["name"] = instance
    global console  # noqa: PLW0603
    console = get_console()
    # Synchronise the base module's output configuration so that display
    # functions use the same console / simple-output mode.
    configure_output(console=console, simple=simple)


def get_client() -> OdooClient:
    """Get configured Odoo client.

    Returns:
        OdooClient instance

    """
    with _handle_errors():
        config = get_config(instance=_instance_config["name"])
        return OdooClient(config)


def _instance_source_label(path: Path) -> str:
    project_instances = Path.cwd() / ".vodoo" / "instances"
    try:
        path.relative_to(project_instances)
        return "project"
    except ValueError:
        return "global"


@config_app.command("list-instances")
def config_list_instances() -> None:
    """List discovered instance profile files and defaults."""
    with _handle_errors():
        profiles = list_instance_profiles()
        project_default = read_default_instance("project")
        global_default = read_default_instance("global")
        selected = resolve_instance(_instance_config["name"])

        names = set(profiles)
        if project_default:
            names.add(project_default)
        if global_default:
            names.add(global_default)
        names.add(selected)

        if not names:
            console.print("[yellow]No instance profiles found[/yellow]")
            return

        table = Table(title="Vodoo Instances")
        table.add_column("Instance", style="cyan")
        table.add_column("Profiles")
        table.add_column("Default")
        table.add_column("Selected")

        for name in sorted(names):
            profile_paths = profiles.get(name, [])
            if profile_paths:
                labels = [_instance_source_label(path) for path in profile_paths]
                profile_text = ", ".join(labels)
            else:
                profile_text = "-"

            defaults: list[str] = []
            if project_default == name:
                defaults.append("project")
            if global_default == name:
                defaults.append("global")

            table.add_row(
                name,
                profile_text,
                ", ".join(defaults) if defaults else "-",
                "yes" if name == selected else "",
            )

        console.print(table)


@config_app.command("show")
def config_show(
    instance: Annotated[
        str | None,
        typer.Option("--instance", "-i", help="Instance/profile name to inspect"),
    ] = None,
) -> None:
    """Show effective configuration (password masked)."""
    with _handle_errors():
        selected_input = instance if instance is not None else _instance_config["name"]
        selected = resolve_instance(selected_input)
        source = detect_config_file(instance=selected_input)
        cfg = get_config(instance=selected_input)

        console.print("[bold cyan]Active Configuration[/bold cyan]")
        console.print(f"instance: {selected}")
        console.print(f"source: {source if source else 'environment'}")
        console.print(f"url: {cfg.url}")
        console.print(f"database: {cfg.database}")
        console.print(f"username: {cfg.username}")
        if cfg.password_ref:
            console.print(f"password_ref: {cfg.password_ref}")
        console.print("password: ***")
        console.print(f"default_user_id: {cfg.default_user_id}")
        console.print(f"retry_count: {cfg.retry_count}")
        console.print(f"retry_backoff: {cfg.retry_backoff}")
        console.print(f"retry_max_backoff: {cfg.retry_max_backoff}")


@config_app.command("use")
def config_use(
    instance: Annotated[str, typer.Argument(help="Instance/profile name")],
    global_default: Annotated[
        bool,
        typer.Option("--global", help="Write default instance to ~/.config/vodoo/default-instance"),
    ] = False,
) -> None:
    """Set the default instance for this project or globally."""
    with _handle_errors():
        scope: Literal["project", "global"] = "global" if global_default else "project"
        target = write_default_instance(instance, scope=scope)
        console.print(f"[green]Default instance set to '{instance}' ({scope})[/green]")
        console.print(f"file: {target}")


@config_app.command("test")
def config_test(
    instance: Annotated[
        str | None,
        typer.Option("--instance", "-i", help="Instance/profile name to test"),
    ] = None,
) -> None:
    """Test authentication with the selected instance."""
    with _handle_errors():
        selected_input = instance if instance is not None else _instance_config["name"]
        cfg = get_config(instance=selected_input)
        selected = resolve_instance(selected_input)

        with OdooClient(cfg) as client:
            uid = client.uid
            transport = "json-2" if client.is_json2 else "json-rpc"

        console.print("[green]Connection test successful[/green]")
        console.print(f"instance: {selected}")
        console.print(f"url: {cfg.url}")
        console.print(f"transport: {transport}")
        console.print(f"uid: {uid}")


# ---------------------------------------------------------------------------
# Shared CLI helpers to avoid copy-paste across domain commands
# ---------------------------------------------------------------------------


def _show_fields(  # noqa: PLR0912
    record_type: str,
    get_record_fn: Callable[..., dict[str, Any]],
    list_fields_fn: Callable[..., dict[str, Any]],
    record_id: int | None = None,
    field_name: str | None = None,
) -> None:
    """Shared implementation for all ``fields`` sub-commands."""
    if record_id:
        record = get_record_fn(record_id)
        console.print(f"\n[bold cyan]Fields for {record_type} #{record_id}[/bold cyan]\n")

        if field_name:
            if field_name in record:
                console.print(f"[bold]{field_name}:[/bold] {record[field_name]}")
            else:
                console.print(f"[yellow]Field '{field_name}' not found[/yellow]")
        else:
            for key, value in sorted(record.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
    else:
        fields = list_fields_fn()
        console.print(f"\n[bold cyan]Available {record_type} Fields[/bold cyan]\n")

        if field_name:
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
            for name, definition in sorted(fields.items()):
                field_type = definition.get("type", "unknown")
                field_label = definition.get("string", name)
                console.print(f"[cyan]{name}[/cyan] ({field_type}) - {field_label}")

            console.print(f"\n[dim]Total: {len(fields)} fields[/dim]")
            console.print("[dim]Use --field-name to see details for a specific field[/dim]")


def _download_all(
    record_type: str,
    record_id: int,
    list_attachments_fn: Callable[..., list[dict[str, Any]]],
    download_fn: Callable[..., list[Any]],
    output_dir: Path | None = None,
    extension: str | None = None,
) -> None:
    """Shared implementation for all ``download-all`` sub-commands."""
    attachments = list_attachments_fn(record_id)
    if not attachments:
        console.print(f"[yellow]No attachments found for {record_type} {record_id}[/yellow]")
        return

    if extension:
        ext = extension.lower().lstrip(".")
        filtered = [att for att in attachments if att.get("name", "").lower().endswith(f".{ext}")]
        if not filtered:
            console.print(
                f"[yellow]No {ext} attachments found for {record_type} {record_id}[/yellow]"
            )
            return
        console.print(f"[cyan]Downloading {len(filtered)} .{ext} attachments...[/cyan]")
    else:
        console.print(f"[cyan]Downloading {len(attachments)} attachments...[/cyan]")

    downloaded_files = download_fn(record_id, output_dir, extension=extension)

    if downloaded_files:
        console.print(f"\n[green]Successfully downloaded {len(downloaded_files)} files:[/green]")
        for file_path in downloaded_files:
            console.print(f"  - {file_path}")
    else:
        console.print("[yellow]No files were downloaded[/yellow]")


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

    with _handle_errors():
        tickets = client.helpdesk.list(domain=domain, limit=limit, fields=fields)
        display_records(tickets, title="Helpdesk Tickets")
        console.print(f"\n[dim]Found {len(tickets)} tickets[/dim]")


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

    with _handle_errors():
        ticket = client.helpdesk.get(ticket_id, fields=fields)

        if fields:
            # If specific fields requested, show them directly
            console.print(f"\n[bold cyan]Ticket #{ticket_id}[/bold cyan]\n")
            for key, value in sorted(ticket.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_record_detail(ticket, show_html=show_html, record_type="Ticket")


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

    with _handle_errors():
        success = client.helpdesk.comment(
            ticket_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added comment to ticket {ticket_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to ticket {ticket_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        success = client.helpdesk.note(
            ticket_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added note to ticket {ticket_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to ticket {ticket_id}[/red]")
            raise typer.Exit(1)


@helpdesk_app.command("tags")
def helpdesk_tags() -> None:
    """List available helpdesk tags."""
    client = get_client()

    with _handle_errors():
        tags = client.helpdesk.tags()
        display_tags(tags)
        console.print(f"\n[dim]Found {len(tags)} tags[/dim]")


@helpdesk_app.command("tag")
def helpdesk_tag(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
    tag_id: Annotated[int, typer.Argument(help="Tag ID")],
) -> None:
    """Add a tag to a ticket."""
    client = get_client()

    with _handle_errors():
        client.helpdesk.add_tag(ticket_id, tag_id)
        console.print(f"[green]Successfully added tag {tag_id} to ticket {ticket_id}[/green]")


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

    with _handle_errors():
        messages = client.helpdesk.messages(ticket_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for ticket {ticket_id}[/yellow]")


@helpdesk_app.command("attachments")
def helpdesk_attachments(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
) -> None:
    """List attachments for a ticket."""
    client = get_client()

    with _handle_errors():
        attachments = client.helpdesk.attachments(ticket_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for ticket {ticket_id}[/yellow]")


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

    with _handle_errors():
        output_path = download_attachment(client, attachment_id, output)
        console.print(f"[green]Downloaded attachment to {output_path}[/green]")


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
    with _handle_errors():
        _download_all(
            "ticket",
            ticket_id,
            client.helpdesk.attachments,
            client.helpdesk.download,
            output_dir=output_dir,
            extension=extension,
        )


@helpdesk_app.command("fields")
def helpdesk_fields(
    ticket_id: Annotated[int | None, typer.Argument(help="Ticket ID (optional)")] = None,
    field_name: Annotated[
        str | None,
        typer.Option(help="Show details for a specific field"),
    ] = None,
) -> None:
    """List available fields or show field values for a specific ticket."""
    client = get_client()
    with _handle_errors():
        _show_fields(
            "Helpdesk Ticket",
            client.helpdesk.get,
            client.helpdesk.fields,
            record_id=ticket_id,
            field_name=field_name,
        )


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

    with _handle_errors():
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, "helpdesk.ticket", ticket_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
        success = client.helpdesk.set(ticket_id, values)
        if success:
            console.print(f"[green]Successfully updated ticket {ticket_id}[/green]")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to set fields on ticket {ticket_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        attachment_id = client.helpdesk.attach(ticket_id, file_path, name=name)
        console.print(
            f"[green]Successfully attached {file_path.name} to ticket {ticket_id}[/green]"
        )
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")

        # Show ticket URL for verification
        url = client.helpdesk.url(ticket_id)
        console.print(f"\n[cyan]View ticket:[/cyan] {url}")


@helpdesk_app.command("url")
def helpdesk_url(
    ticket_id: Annotated[int, typer.Argument(help="Ticket ID")],
) -> None:
    """Get the web URL for a ticket."""
    client = get_client()

    with _handle_errors():
        url = client.helpdesk.url(ticket_id)
        console.print(url)


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

    with _handle_errors():
        tasks = client.tasks.list(domain=domain, limit=limit, fields=fields)
        display_records(tasks, title="Project Tasks")
        console.print(f"\n[dim]Found {len(tasks)} tasks[/dim]")


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

    with _handle_errors():
        task_id = client.tasks.create(
            name=name,
            project_id=project_id,
            description=description,
            user_ids=user_id,
            tag_ids=tag_id,
            parent_id=parent_id,
        )
        console.print(f"[green]Successfully created task '{name}' with ID {task_id}[/green]")

        # Show the URL
        url = client.tasks.url(task_id)
        console.print(f"\n[cyan]View task:[/cyan] {url}")


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

    with _handle_errors():
        task = client.tasks.get(task_id, fields=fields)

        if fields:
            # If specific fields requested, show them directly
            console.print(f"\n[bold cyan]Task #{task_id}[/bold cyan]\n")
            for key, value in sorted(task.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_record_detail(task, show_html=show_html, record_type="Task")


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

    with _handle_errors():
        success = client.tasks.comment(
            task_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added comment to task {task_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to task {task_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        success = client.tasks.note(task_id, message, user_id=author_id, markdown=not no_markdown)
        if success:
            console.print(f"[green]Successfully added note to task {task_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to task {task_id}[/red]")
            raise typer.Exit(1)


@project_task_app.command("tags")
def project_tags() -> None:
    """List available project tags."""
    client = get_client()

    with _handle_errors():
        tags = client.tasks.tags()
        display_tags(tags, title="Project Tags")
        console.print(f"\n[dim]Found {len(tags)} tags[/dim]")


@project_task_app.command("tag")
def project_tag(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
    tag_id: Annotated[int, typer.Argument(help="Tag ID")],
) -> None:
    """Add a tag to a task."""
    client = get_client()

    with _handle_errors():
        client.tasks.add_tag(task_id, tag_id)
        console.print(f"[green]Successfully added tag {tag_id} to task {task_id}[/green]")


@project_task_app.command("tag-create")
def project_tag_create(
    name: Annotated[str, typer.Argument(help="Tag name")],
    color: Annotated[int | None, typer.Option(help="Tag color index (0-11)")] = None,
) -> None:
    """Create a new project tag."""
    client = get_client()

    with _handle_errors():
        tag_id = client.tasks.create_tag(name, color=color)
        console.print(f"[green]Successfully created tag '{name}' with ID {tag_id}[/green]")


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

    with _handle_errors():
        success = client.tasks.delete_tag(tag_id)
        if success:
            console.print(f"[green]Successfully deleted tag {tag_id}[/green]")
        else:
            console.print(f"[red]Failed to delete tag {tag_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        messages = client.tasks.messages(task_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for task {task_id}[/yellow]")


@project_task_app.command("attachments")
def project_attachments(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
) -> None:
    """List attachments for a task."""
    client = get_client()

    with _handle_errors():
        attachments = client.tasks.attachments(task_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for task {task_id}[/yellow]")


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

    with _handle_errors():
        output_path = download_attachment(client, attachment_id, output)
        console.print(f"[green]Downloaded attachment to {output_path}[/green]")


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
    with _handle_errors():
        _download_all(
            "task",
            task_id,
            client.tasks.attachments,
            client.tasks.download,
            output_dir=output_dir,
            extension=extension,
        )


@project_task_app.command("fields")
def project_fields(
    task_id: Annotated[int | None, typer.Argument(help="Task ID (optional)")] = None,
    field_name: Annotated[
        str | None,
        typer.Option(help="Show details for a specific field"),
    ] = None,
) -> None:
    """List available fields or show field values for a specific task."""
    client = get_client()
    with _handle_errors():
        _show_fields(
            "Project Task",
            client.tasks.get,
            client.tasks.fields,
            record_id=task_id,
            field_name=field_name,
        )


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

    with _handle_errors():
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, "project.task", task_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
        success = client.tasks.set(task_id, values)
        if success:
            console.print(f"[green]Successfully updated task {task_id}[/green]")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to set fields on task {task_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        attachment_id = client.tasks.attach(task_id, file_path, name=name)
        console.print(f"[green]Successfully attached {file_path.name} to task {task_id}[/green]")
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")

        # Show task URL for verification
        url = client.tasks.url(task_id)
        console.print(f"\n[cyan]View task:[/cyan] {url}")


@project_task_app.command("url")
def project_url(
    task_id: Annotated[int, typer.Argument(help="Task ID")],
) -> None:
    """Get the web URL for a task."""
    client = get_client()

    with _handle_errors():
        url = client.tasks.url(task_id)
        console.print(url)


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

    with _handle_errors():
        projects = client.projects.list(domain=domain, limit=limit, fields=fields)
        display_records(projects, title="Projects")
        console.print(f"\n[dim]Found {len(projects)} projects[/dim]")


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

    with _handle_errors():
        project = client.projects.get(project_id, fields=fields)

        if fields:
            # If specific fields requested, show them directly
            console.print(f"\n[bold cyan]Project #{project_id}[/bold cyan]\n")
            for key, value in sorted(project.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_record_detail(project, show_html=show_html, record_type="Project")


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

    with _handle_errors():
        success = client.projects.comment(
            project_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added comment to project {project_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to project {project_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        success = client.projects.note(
            project_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added note to project {project_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to project {project_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        messages = client.projects.messages(project_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for project {project_id}[/yellow]")


@project_project_app.command("attachments")
def project_project_attachments(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
) -> None:
    """List attachments for a project."""
    client = get_client()

    with _handle_errors():
        attachments = client.projects.attachments(project_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for project {project_id}[/yellow]")


@project_project_app.command("fields")
def project_project_fields(
    project_id: Annotated[int | None, typer.Argument(help="Project ID (optional)")] = None,
    field_name: Annotated[
        str | None,
        typer.Option(help="Show details for a specific field"),
    ] = None,
) -> None:
    """List available fields or show field values for a specific project."""
    client = get_client()
    with _handle_errors():
        _show_fields(
            "Project",
            client.projects.get,
            client.projects.fields,
            record_id=project_id,
            field_name=field_name,
        )


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

    with _handle_errors():
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, "project.project", project_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
        success = client.projects.set(project_id, values)
        if success:
            console.print(f"[green]Successfully updated project {project_id}[/green]")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to set fields on project {project_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        attachment_id = client.projects.attach(project_id, file_path, name=name)
        console.print(
            f"[green]Successfully attached {file_path.name} to project {project_id}[/green]"
        )
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")

        # Show project URL for verification
        url = client.projects.url(project_id)
        console.print(f"\n[cyan]View project:[/cyan] {url}")


@project_project_app.command("url")
def project_project_url(
    project_id: Annotated[int, typer.Argument(help="Project ID")],
) -> None:
    """Get the web URL for a project."""
    client = get_client()

    with _handle_errors():
        url = client.projects.url(project_id)
        console.print(url)


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

    with _handle_errors():
        stages = client.projects.stages(project_id=project_id)
        if stages:
            display_stages(stages)
            console.print(f"\n[dim]Found {len(stages)} stages[/dim]")
        elif project_id:
            console.print(f"[yellow]No stages found for project {project_id}[/yellow]")
        else:
            console.print("[yellow]No stages found[/yellow]")


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

    with _handle_errors():
        articles = client.knowledge.list(domain=domain, limit=limit)
        display_records(articles, title="Knowledge Articles")
        console.print(f"\n[dim]Found {len(articles)} articles[/dim]")


@knowledge_app.command("show")
def knowledge_show(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
    show_html: Annotated[
        bool, typer.Option("--html", help="Show raw HTML content instead of markdown")
    ] = False,
) -> None:
    """Show detailed article information."""
    client = get_client()

    with _handle_errors():
        article = client.knowledge.get(article_id)
        display_article_detail(article, show_html=show_html)


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

    with _handle_errors():
        success = client.knowledge.comment(
            article_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added comment to article {article_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to article {article_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        success = client.knowledge.note(
            article_id, message, user_id=author_id, markdown=not no_markdown
        )
        if success:
            console.print(f"[green]Successfully added note to article {article_id}[/green]")
        else:
            console.print(f"[red]Failed to add note to article {article_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        messages = client.knowledge.messages(article_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for article {article_id}[/yellow]")


@knowledge_app.command("attachments")
def knowledge_attachments(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
) -> None:
    """List attachments for an article."""
    client = get_client()

    with _handle_errors():
        attachments = client.knowledge.attachments(article_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for article {article_id}[/yellow]")


@knowledge_app.command("url")
def knowledge_url(
    article_id: Annotated[int, typer.Argument(help="Article ID")],
) -> None:
    """Get the web URL for an article."""
    client = get_client()

    with _handle_errors():
        url = client.knowledge.url(article_id)
        console.print(url)


# Security commands


@security_app.command("create-groups")
def security_create_groups() -> None:
    """Create or reuse the standard Vodoo security groups."""
    client = get_client()

    with _handle_errors():
        group_ids, warnings = client.security.create_groups()
        console.print("[green]Security groups ready:[/green]")
        for name, group_id in group_ids.items():
            console.print(f"- {name}: {group_id}")

        if warnings:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in warnings:
                console.print(f"- {warning}")


@security_app.command("assign-bot")
def security_assign_bot(
    user_id: Annotated[
        int | None,
        typer.Option("--user-id", "-u", help="User ID of the bot account"),
    ] = None,
    login: Annotated[
        str | None,
        typer.Option("--login", help="User login/email for the bot account"),
    ] = None,
    create_groups: Annotated[
        bool,
        typer.Option(
            "--create-groups/--no-create-groups",
            help="Ensure Vodoo API groups exist before assigning",
        ),
    ] = True,
    keep_default_groups: Annotated[
        bool,
        typer.Option(
            "--keep-default-groups",
            help="Do not remove base.group_user or base.group_portal",
        ),
    ] = False,
) -> None:
    """Assign a bot user to all Vodoo API security groups."""
    client = get_client()

    with _handle_errors():
        resolved_user_id = client.security.resolve_user(user_id=user_id, login=login)
        group_names = [group.name for group in GROUP_DEFINITIONS]

        if create_groups:
            group_ids, warnings = client.security.create_groups()
        else:
            group_ids, warnings = client.security.get_group_ids(group_names)

        missing_groups = [name for name in group_names if name not in group_ids]
        if missing_groups:
            missing_list = ", ".join(missing_groups)
            console.print(f"[red]Missing groups:[/red] {missing_list}")
            raise typer.Exit(1)

        client.security.assign(
            resolved_user_id,
            list(group_ids.values()),
            remove_default_groups=not keep_default_groups,
        )

        console.print(
            f"[green]Assigned user {resolved_user_id} to {len(group_ids)} groups.[/green]"
        )
        if warnings:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in warnings:
                console.print(f"- {warning}")


@security_app.command("create-user")
def security_create_user(
    name: Annotated[str, typer.Argument(help="User's display name")],
    login: Annotated[str, typer.Argument(help="User's login (usually email)")],
    password: Annotated[
        str | None,
        typer.Option("--password", "-p", help="User's password (generated if not provided)"),
    ] = None,
    email: Annotated[
        str | None,
        typer.Option("--email", "-e", help="User's email (defaults to login)"),
    ] = None,
    assign_groups: Annotated[
        bool,
        typer.Option(
            "--assign-groups/--no-assign-groups",
            help="Assign user to all Vodoo API security groups",
        ),
    ] = False,
    create_groups: Annotated[
        bool,
        typer.Option(
            "--create-groups/--no-create-groups",
            help="Create Vodoo API groups if they don't exist (requires --assign-groups)",
        ),
    ] = True,
) -> None:
    """Create a new API service account user.

    Creates a share user (not billed) with no default groups.
    Optionally assigns to all Vodoo API security groups.

    NOTE: Requires admin credentials (Access Rights group).

    Examples:
        vodoo security create-user "Bot User" bot@example.com
        vodoo security create-user "Bot User" bot@example.com --password MySecretPass123
        vodoo security create-user "Bot User" bot@example.com --assign-groups

        # With admin credentials:
        ODOO_USERNAME=admin@example.com ODOO_PASSWORD=... vodoo security create-user ...
    """
    client = get_client()

    with _handle_errors():
        user_id, generated_password = client.security.create_user(
            name=name,
            login=login,
            password=password,
            email=email,
        )

        console.print(f"[green]Created user:[/green] {name} (id={user_id})")
        console.print(f"[bold]Login:[/bold] {login}")
        if password is None:
            console.print(f"[bold]Password:[/bold] {generated_password}")
            console.print("[yellow]⚠ Save this password - it cannot be retrieved later![/yellow]")

        # Get user info to show share status
        user_info = client.security.get_user(user_id)
        console.print(f"[bold]Share (not billed):[/bold] {user_info['share']}")

        if assign_groups:
            group_names = [group.name for group in GROUP_DEFINITIONS]

            if create_groups:
                group_ids, warnings = client.security.create_groups()
            else:
                group_ids, warnings = client.security.get_group_ids(group_names)

            missing_groups = [name for name in group_names if name not in group_ids]
            if missing_groups:
                missing_list = ", ".join(missing_groups)
                console.print(f"[yellow]Missing groups (skipped):[/yellow] {missing_list}")

            if group_ids:
                client.security.assign(
                    user_id,
                    list(group_ids.values()),
                    remove_default_groups=True,
                )
                console.print(f"[green]Assigned to {len(group_ids)} groups:[/green]")
                for group_name in group_ids:
                    console.print(f"  - {group_name}")

            if warnings:
                console.print("\n[yellow]Warnings:[/yellow]")
                for warning in warnings:
                    console.print(f"  - {warning}")


@security_app.command("set-password")
def security_set_password(
    user_id: Annotated[
        int | None,
        typer.Option("--user-id", "-u", help="User ID"),
    ] = None,
    login: Annotated[
        str | None,
        typer.Option("--login", "-l", help="User login/email"),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", "-p", help="New password (generated if not provided)"),
    ] = None,
) -> None:
    """Set or reset a user's password.

    NOTE: Requires admin credentials (Access Rights group).

    Examples:
        vodoo security set-password --login bot@example.com
        vodoo security set-password --user-id 42 --password MyNewPassword123
    """
    client = get_client()

    with _handle_errors():
        resolved_user_id = client.security.resolve_user(user_id=user_id, login=login)

        new_password = client.security.set_password(resolved_user_id, password)

        # Get user info for display
        user_info = client.security.get_user(resolved_user_id)

        console.print(
            f"[green]Password updated for:[/green] {user_info['name']} (id={resolved_user_id})"
        )
        console.print(f"[bold]Login:[/bold] {user_info['login']}")
        if password is None:
            console.print(f"[bold]New password:[/bold] {new_password}")
            console.print("[yellow]⚠ Save this password - it cannot be retrieved later![/yellow]")
        else:
            console.print("[green]Password set to provided value.[/green]")


# Generic model commands


@model_app.command("create")
def model_create(
    model: Annotated[str, typer.Argument(help="Model name (e.g., product.template)")],
    fields: Annotated[
        list[str],
        typer.Argument(help="Field assignments in format 'field=value'"),
    ],
) -> None:
    """Create a new record in any model.

    Examples:
        vodoo model create product.template name="My Product" list_price=29.99

        vodoo model create res.partner name="John Doe" email=john@example.com

        vodoo model create project.task name="New Task" project_id=10
    """
    client = get_client()

    # Parse field assignments
    values: dict[str, Any] = {}
    with _handle_errors():
        for field_assignment in fields:
            # Parse using existing helper
            field, value = parse_field_assignment(client, model, 0, field_assignment)
            values[field] = value
        record_id = client.generic.create(model, values)
        console.print(f"[green]Successfully created record with ID {record_id}[/green]")
        console.print(f"Model: {model}")
        for field, value in values.items():
            console.print(f"  {field} = {value}")


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
        vodoo model read product.template 42

        # Search records
        vodoo model read product.template --domain='[["list_price",">","20.00"]]'

        # With specific fields
        vodoo model read res.partner --field name --field email --limit 10
    """
    client = get_client()

    with _handle_errors():
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

            records = client.generic.search(
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
        vodoo model update product.template 42 list_price=39.99 active=true

        vodoo model update res.partner 123 name="Jane Doe" phone="+1234567890"
    """
    client = get_client()

    # Parse field assignments
    values: dict[str, Any] = {}
    with _handle_errors():
        for field_assignment in fields:
            field, value = parse_field_assignment(
                client, model, record_id, field_assignment, no_markdown=no_markdown
            )
            values[field] = value
        success = client.generic.update(model, record_id, values)
        if success:
            console.print(f"[green]Successfully updated record {record_id}[/green]")
            console.print(f"Model: {model}")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to update record {record_id}[/red]")
            raise typer.Exit(1)


@model_app.command("delete")
def model_delete(
    model: Annotated[str, typer.Argument(help="Model name")],
    record_id: Annotated[int, typer.Argument(help="Record ID")],
) -> None:
    """Delete a record from any model.

    Examples:
        vodoo model delete product.template 42
    """
    client = get_client()

    with _handle_errors():
        success = client.generic.delete(model, record_id)
        if success:
            console.print(f"[green]Successfully deleted record {record_id} from {model}[/green]")
        else:
            console.print(f"[red]Failed to delete record {record_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        args = json.loads(args_json)
        kwargs = json.loads(kwargs_json)

        result = client.generic.call(
            model,
            method,
            args=args,
            kwargs=kwargs,
        )

        console.print("[green]Method executed successfully[/green]")
        console.print(f"Result: {result}")


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

    with _handle_errors():
        leads = client.crm.list(domain=domain, limit=limit, fields=fields)
        display_records(leads, title="CRM Leads")
        console.print(f"\n[dim]Found {len(leads)} leads/opportunities[/dim]")


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

    with _handle_errors():
        lead = client.crm.get(lead_id, fields=fields)
        if fields:
            console.print(f"\n[bold cyan]Lead #{lead_id}[/bold cyan]\n")
            for key, value in sorted(lead.items()):
                console.print(f"[bold]{key}:[/bold] {value}")
        else:
            display_record_detail(lead, show_html=show_html, record_type="Lead")


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

    with _handle_errors():
        success = client.crm.comment(lead_id, message, user_id=author_id, markdown=not no_markdown)
        if success:
            console.print(f"[green]Successfully added comment to lead {lead_id}[/green]")
        else:
            console.print(f"[red]Failed to add comment to lead {lead_id}[/red]")
            raise typer.Exit(1)


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

    with _handle_errors():
        success = client.crm.note(lead_id, message, user_id=author_id, markdown=not no_markdown)
        if success:
            console.print(f"[green]Successfully added note to lead {lead_id}[/green]")
        else:
            raise typer.Exit(1)


@crm_app.command("tags")
def crm_tags() -> None:
    """List available CRM tags."""
    client = get_client()

    with _handle_errors():
        tags = client.crm.tags()
        display_tags(tags)
        console.print(f"\n[dim]Found {len(tags)} tags[/dim]")


@crm_app.command("tag")
def crm_tag(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    tag_id: Annotated[int, typer.Argument(help="Tag ID")],
) -> None:
    """Add a tag to a lead."""
    client = get_client()

    with _handle_errors():
        client.crm.add_tag(lead_id, tag_id)
        console.print(f"[green]Successfully added tag {tag_id} to lead {lead_id}[/green]")


@crm_app.command("chatter")
def crm_chatter(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    limit: Annotated[int | None, typer.Option(help="Max messages to show")] = None,
    show_html: Annotated[bool, typer.Option("--html", help="Show raw HTML")] = False,
) -> None:
    """Show message history/chatter for a lead."""
    client = get_client()

    with _handle_errors():
        messages = client.crm.messages(lead_id, limit=limit)
        if messages:
            display_messages(messages, show_html=show_html)
        else:
            console.print(f"[yellow]No messages found for lead {lead_id}[/yellow]")


@crm_app.command("attachments")
def crm_attachments(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
) -> None:
    """List attachments for a lead."""
    client = get_client()

    with _handle_errors():
        attachments = client.crm.attachments(lead_id)
        if attachments:
            display_attachments(attachments)
            console.print(f"\n[dim]Found {len(attachments)} attachments[/dim]")
        else:
            console.print(f"[yellow]No attachments found for lead {lead_id}[/yellow]")


@crm_app.command("download")
def crm_download(
    attachment_id: Annotated[int, typer.Argument(help="Attachment ID")],
    output: Annotated[Path | None, typer.Option(help="Output file path")] = None,
) -> None:
    """Download a single attachment by ID."""
    client = get_client()

    with _handle_errors():
        output_path = download_attachment(client, attachment_id, output)
        console.print(f"[green]Downloaded attachment to {output_path}[/green]")


@crm_app.command("download-all")
def crm_download_all(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (defaults to current directory)"),
    ] = None,
    extension: Annotated[
        str | None,
        typer.Option("--extension", "--ext", help="Filter by file extension (e.g., pdf, jpg, png)"),
    ] = None,
) -> None:
    """Download all attachments from a lead."""
    client = get_client()
    with _handle_errors():
        _download_all(
            "lead",
            lead_id,
            client.crm.attachments,
            client.crm.download,
            output_dir=output_dir,
            extension=extension,
        )


@crm_app.command("fields")
def crm_fields(
    lead_id: Annotated[int | None, typer.Argument(help="Lead ID (optional)")] = None,
    field_name: Annotated[str | None, typer.Option(help="Show specific field")] = None,
) -> None:
    """List available fields or show field values for a specific lead."""
    client = get_client()
    with _handle_errors():
        _show_fields(
            "CRM Lead",
            client.crm.get,
            client.crm.fields,
            record_id=lead_id,
            field_name=field_name,
        )


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
    with _handle_errors():
        for fa in fields:
            field, value = parse_field_assignment(
                client, "crm.lead", lead_id, fa, no_markdown=no_markdown
            )
            values[field] = value
        success = client.crm.set(lead_id, values)
        if success:
            console.print(f"[green]Successfully updated lead {lead_id}[/green]")
            for field, value in values.items():
                console.print(f"  {field} = {value}")
        else:
            console.print(f"[red]Failed to update lead {lead_id}[/red]")
            raise typer.Exit(1)


@crm_app.command("attach")
def crm_attach(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
    file_path: Annotated[Path, typer.Argument(help="Path to file to attach")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Custom name")] = None,
) -> None:
    """Attach a file to a lead."""
    client = get_client()

    with _handle_errors():
        attachment_id = client.crm.attach(lead_id, file_path, name=name)
        console.print(f"[green]Successfully attached {file_path.name} to lead {lead_id}[/green]")
        console.print(f"[dim]Attachment ID: {attachment_id}[/dim]")
        url = client.crm.url(lead_id)
        console.print(f"\n[cyan]View lead:[/cyan] {url}")


@crm_app.command("url")
def crm_url(
    lead_id: Annotated[int, typer.Argument(help="Lead/Opportunity ID")],
) -> None:
    """Get the web URL for a lead."""
    client = get_client()

    with _handle_errors():
        url = client.crm.url(lead_id)
        console.print(url)


# Timer commands


@timer_app.command("status")
def timer_status() -> None:
    """Show today's timesheets and running timers."""
    client = get_client()

    with _handle_errors():
        timesheets = client.timer.list()
        if not timesheets:
            console.print("[yellow]No timesheets found for today[/yellow]")
            return

        from rich.table import Table

        table = Table(title="Today's Timesheets")
        table.add_column("ID", style="cyan")
        table.add_column("State", style="bold")
        table.add_column("Source", style="green")
        table.add_column("Project", style="blue")
        table.add_column("Elapsed", style="yellow", justify="right")
        table.add_column("Description", style="dim")

        for ts in timesheets:
            state_icon = "▶️" if ts.state.value == "running" else "⏹"
            state_style = "bold green" if ts.state.value == "running" else "dim"
            table.add_row(
                str(ts.id),
                f"[{state_style}]{state_icon} {ts.state.value}[/{state_style}]",
                ts.display_label,
                ts.project_name or "",
                ts.elapsed_formatted,
                ts.name or "",
            )

        console.print(table)

        active = [ts for ts in timesheets if ts.state.value == "running"]
        console.print(f"\n[dim]{len(timesheets)} timesheets, {len(active)} running[/dim]")


@timer_app.command("start")
def timer_start(
    record_id: Annotated[int, typer.Argument(help="Task, ticket, or timesheet ID")],
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Source type: 'task', 'ticket', or 'timesheet' (default: task)",
        ),
    ] = "task",
) -> None:
    """Start a timer on a task, ticket, or timesheet.

    Examples:
        vodoo timer start 42                    # Start timer on task 42
        vodoo timer start 42 --source task      # Same as above
        vodoo timer start 10 --source ticket    # Start timer on ticket 10
        vodoo timer start 99 --source timesheet # Start on existing timesheet
    """
    client = get_client()

    with _handle_errors():
        if source == "task":
            client.timer.start_task(record_id)
            console.print(f"[green]▶ Started timer on task {record_id}[/green]")
        elif source == "ticket":
            client.timer.start_ticket(record_id)
            console.print(f"[green]▶ Started timer on ticket {record_id}[/green]")
        elif source == "timesheet":
            client.timer.start_timesheet(record_id)
            console.print(f"[green]▶ Started timer on timesheet {record_id}[/green]")
        else:
            console.print(f"[red]Unknown source type: {source}[/red]")
            console.print("[dim]Use: task, ticket, or timesheet[/dim]")
            raise typer.Exit(1)


@timer_app.command("stop")
def timer_stop(
    timesheet_id: Annotated[
        int | None,
        typer.Argument(help="Timesheet ID to stop (omit to stop all running timers)"),
    ] = None,
) -> None:
    """Stop a running timer.

    If no timesheet ID is given, stops all currently running timers.

    Examples:
        vodoo timer stop         # Stop all running timers
        vodoo timer stop 99      # Stop timer on timesheet 99
    """
    client = get_client()

    with _handle_errors():
        if timesheet_id is not None:
            client.timer.stop_timesheet(timesheet_id)
            console.print(f"[green]⏹ Stopped timer on timesheet {timesheet_id}[/green]")
        else:
            stopped = client.timer.stop()
            if stopped:
                console.print(f"[green]⏹ Stopped {len(stopped)} timer(s):[/green]")
                for ts in stopped:
                    console.print(f"  - {ts.display_label} ({ts.elapsed_formatted})")
            else:
                console.print("[yellow]No running timers to stop[/yellow]")


@timer_app.command("active")
def timer_active() -> None:
    """Show only currently running timers."""
    client = get_client()

    with _handle_errors():
        active = client.timer.active()
        if not active:
            console.print("[yellow]No running timers[/yellow]")
            return

        from rich.table import Table

        table = Table(title="Running Timers")
        table.add_column("ID", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("Project", style="blue")
        table.add_column("Elapsed", style="yellow", justify="right")

        for ts in active:
            table.add_row(
                str(ts.id),
                ts.display_label,
                ts.project_name or "",
                ts.elapsed_formatted,
            )

        console.print(table)


if __name__ == "__main__":
    app()
