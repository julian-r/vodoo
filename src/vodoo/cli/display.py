"""Presentation helpers used by the Vodoo CLI.

Core domain modules expose deprecated lazy shims for these historical helpers.
"""

from __future__ import annotations

from typing import Any

from vodoo.base import _html_to_markdown
from vodoo.cli.output import (
    get_console as _get_console,
)
from vodoo.cli.output import (
    is_simple_output as _is_simple_output,
)
from vodoo.cli.output import (
    is_structured_output,
    structured_print,
    write,
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
    """Display records in a table, TSV, or JSON format.

    Args:
        records: List of record dictionaries
        title: Table title

    """
    if is_structured_output():
        structured_print(records)
        return

    if not records:
        if _is_simple_output():
            write("No records found")
        else:
            _get_console().print("[yellow]No records found[/yellow]")
        return

    field_names = list(records[0].keys())

    if _is_simple_output():
        # Simple TSV output for LLMs
        write("\t".join(field_names))
        for record in records:
            row = [_format_field_value(record.get(f)) for f in field_names]
            write("\t".join(row))
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
    if is_structured_output():
        structured_print(record)
        return

    if _is_simple_output():
        # Simple key: value format
        write(f"id: {record['id']}")
        write(f"name: {record['name']}")
        if record.get("partner_id"):
            write(f"partner: {record['partner_id'][1]}")
        if record.get("stage_id"):
            write(f"stage: {record['stage_id'][1]}")
        if record.get("user_id"):
            write(f"assigned_to: {record['user_id'][1]}")
        if record.get("project_id"):
            write(f"project: {record['project_id'][1]}")
        if "priority" in record:
            write(f"priority: {record.get('priority', '0')}")
        if record.get("description"):
            desc = record["description"]
            if not show_html:
                desc = _html_to_markdown(desc)
            write(f"description: {desc}")
        if record.get("tag_ids"):
            write(f"tags: {','.join(map(str, record['tag_ids']))}")
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


def display_tags(tags: list[dict[str, Any]], title: str = "Tags") -> None:
    """Display tags in a table, TSV, or JSON format.

    Args:
        tags: List of tag dictionaries
        title: Table title

    """
    if is_structured_output():
        structured_print(tags)
        return

    if _is_simple_output():
        write("id\tname\tcolor")
        for tag in tags:
            write(f"{tag['id']}\t{tag['name']}\t{tag.get('color', '')}")
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

    if is_structured_output():
        structured_print(messages)
        return

    if not messages:
        write("No messages found") if _is_simple_output() else _get_console().print(
            "[yellow]No messages found[/yellow]"
        )
        return

    if _is_simple_output():
        # Simple format: date, author, type, body (one line per message)
        write("date\tauthor\ttype\tbody")
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
            write(f"{date}\t{author_name}\t{subtype_name}\t{body}")
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


def display_attachments(attachments: list[dict[str, Any]]) -> None:
    """Display attachments in a table, TSV, or JSON format.

    Args:
        attachments: List of attachment dictionaries

    """
    if is_structured_output():
        structured_print(attachments)
        return

    if _is_simple_output():
        write("id\tname\tsize_kb\tmimetype\tcreate_date")
        for att in attachments:
            size = att.get("file_size", 0)
            size_kb = f"{size / 1024:.1f}" if size else ""
            name = att.get("name", "")
            mime = att.get("mimetype", "")
            created = att.get("create_date", "")
            write(f"{att['id']}\t{name}\t{size_kb}\t{mime}\t{created}")
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


def display_crm_stages(stages: list[dict[str, Any]]) -> None:
    """Display CRM pipeline stages in a table, TSV, or structured format."""
    if is_structured_output():
        structured_print(stages)
        return

    if _is_simple_output():
        write("id\tname\tsequence\tis_won\tfold")
        for s in stages:
            won = "true" if s.get("is_won") else "false"
            fold = "true" if s.get("fold") else "false"
            write(f"{s['id']}\t{s['name']}\t{s.get('sequence', '')}\t{won}\t{fold}")
    else:
        from rich.table import Table

        console = _get_console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Sequence", justify="right")
        table.add_column("Won", justify="center")
        table.add_column("Folded", justify="center")

        for s in stages:
            table.add_row(
                str(s["id"]),
                s["name"],
                str(s.get("sequence", "")),
                "✓" if s.get("is_won") else "",
                "✓" if s.get("fold") else "",
            )

        console.print(table)


def _fmt_currency(value: float) -> str:
    """Format a number as currency-like string."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M"
    if value >= 1_000:
        return f"{value:,.0f}"
    return f"{value:,.0f}"


def _fmt_days(days: int) -> str:
    return f"{days}d"


def display_pipeline(
    summary: dict[str, Any],
    *,
    show_deals: bool = False,
    show_health: bool = False,
    health_flags: list[dict[str, Any]] | None = None,
) -> None:
    """Display pipeline summary in table, TSV, or structured format."""
    if is_structured_output():
        output: dict[str, Any] = {
            "team": summary["team"],
            "date": summary["date"],
            "stages": summary["stages"],
            "totals": summary["totals"],
        }
        if show_deals:
            output["deals"] = summary["deals"]
        if show_health and health_flags:
            output["health"] = health_flags
        structured_print(output)
        return

    if _is_simple_output():
        _display_pipeline_simple(summary, show_deals, show_health, health_flags)
        return

    _display_pipeline_rich(summary, show_deals, show_health, health_flags)


def _display_pipeline_simple(
    summary: dict[str, Any],
    show_deals: bool,
    show_health: bool,
    health_flags: list[dict[str, Any]] | None,
) -> None:
    write(f"# Pipeline: {summary['team']}  {summary['date']}")
    write("stage\tdeals\trevenue\tweighted\tavg_age\toldest")
    for s in summary["stages"]:
        write(
            f"{s['name']}\t{s['deals']}\t{s['revenue']}\t{s['weighted']}"
            f"\t{s['avg_age_days']}\t{s['oldest_days']}"
        )
    t = summary["totals"]
    write(f"TOTAL\t{t['deals']}\t{t['revenue']}\t{t['weighted']}\t\t")

    if show_deals:
        write("\n# Deals")
        write("id\tname\tstage\trevenue\tprobability\tage\tuser")
        for d in summary["deals"]:
            write(
                f"{d['id']}\t{d['name']}\t{d['stage_name']}"
                f"\t{d['expected_revenue']}\t{d['probability']}"
                f"\t{d['age_days']}\t{d.get('user', '')}"
            )

    if show_health and health_flags:
        write("\n# Health")
        write("severity\trule\tdeal_id\tdeal_name\tdetail")
        for f in health_flags:
            write(f"{f['severity']}\t{f['rule']}\t{f['deal_id']}\t{f['deal_name']}\t{f['detail']}")


def _display_pipeline_rich(
    summary: dict[str, Any],
    show_deals: bool,
    show_health: bool,
    health_flags: list[dict[str, Any]] | None,
) -> None:
    from rich.table import Table

    console = _get_console()

    console.print(f"\n[bold]Pipeline: {summary['team']}[/bold]  [dim]{summary['date']}[/dim]\n")

    table = Table(show_header=True, header_style="bold magenta", show_footer=True)
    table.add_column("Stage", style="green", footer_style="bold")
    table.add_column("Deals", justify="right", footer_style="bold")
    table.add_column("Revenue", justify="right", footer_style="bold")
    table.add_column("Weighted", justify="right", footer_style="bold")
    table.add_column("Avg Age", justify="right")
    table.add_column("Oldest", justify="right")

    for s in summary["stages"]:
        table.add_row(
            s["name"],
            str(s["deals"]),
            _fmt_currency(s["revenue"]),
            _fmt_currency(s["weighted"]),
            _fmt_days(s["avg_age_days"]),
            _fmt_days(s["oldest_days"]),
        )

    t = summary["totals"]
    table.columns[0].footer = "Total"
    table.columns[1].footer = str(t["deals"])
    table.columns[2].footer = _fmt_currency(t["revenue"])
    table.columns[3].footer = _fmt_currency(t["weighted"])

    console.print(table)

    # --deals: individual deals under each stage
    if show_deals:
        console.print()
        stage_deals: dict[int, list[dict[str, Any]]] = {}
        for d in summary["deals"]:
            stage_deals.setdefault(d["stage_id"], []).append(d)

        for s in summary["stages"]:
            sid = s["stage_id"]
            deals = stage_deals.get(sid, [])
            console.print(
                f"\n[bold]{s['name']}[/bold]"
                f" [dim]({s['deals']} deals, {_fmt_currency(s['revenue'])})[/dim]"
            )
            for d in deals:
                flags = ""
                if d["expected_revenue"] == 0 and s != summary["stages"][0]:
                    flags += " [yellow]NO-REV[/yellow]"
                if d["probability"] == 0:
                    flags += " [red]0-PROB[/red]"
                user = d.get("user") or "[dim]unassigned[/dim]"
                console.print(
                    f"  [cyan]#{d['id']}[/cyan]  {d['name']:<30}"
                    f"  {_fmt_currency(d['expected_revenue']):>10}"
                    f"  {d['probability']:>3.0f}%"
                    f"  {_fmt_days(d['age_days']):>5}"
                    f"  {user}{flags}"
                )

    # --health: flagged issues
    if show_health and health_flags:
        console.print("\n[bold]Health Flags[/bold]\n")
        htable = Table(show_header=True, header_style="bold")
        htable.add_column("Severity")
        htable.add_column("Rule")
        htable.add_column("Deal")
        htable.add_column("Detail")

        severity_styles = {
            "critical": "bold red",
            "warning": "yellow",
            "info": "dim",
        }
        for f in health_flags:
            style = severity_styles.get(f["severity"], "")
            htable.add_row(
                f"[{style}]{f['severity'].upper()}[/{style}]",
                f["rule"],
                f"#{f['deal_id']} {f['deal_name']}",
                f["detail"],
            )

        console.print(htable)
    elif show_health:
        console.print("\n[green]No health issues found.[/green]")


def display_article_detail(article: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed knowledge article information with body content."""
    if is_structured_output():
        structured_print(article)
        return

    if _is_simple_output():
        write(f"id: {article['id']}")
        write(f"name: {article.get('icon', '')} {article['name']}")
        if article.get("parent_id"):
            write(f"parent: {article['parent_id'][1]}")
        if article.get("category"):
            write(f"category: {article['category']}")
        if article.get("body"):
            body = article["body"] if show_html else _html_to_markdown(article["body"])
            write(f"body: {body}")
    else:
        console = _get_console()
        console.print(f"\n[bold cyan]Article #{article['id']}[/bold cyan]")
        console.print(f"[bold]Title:[/bold] {article.get('icon', '')} {article['name']}")

        if article.get("parent_id"):
            console.print(f"[bold]Parent:[/bold] {article['parent_id'][1]}")

        if article.get("category"):
            console.print(f"[bold]Category:[/bold] {article['category']}")

        if article.get("body"):
            body = article["body"]
            if show_html:
                console.print(f"\n[bold]Content:[/bold]\n{body}")
            else:
                markdown_text = _html_to_markdown(body)
                console.print(f"\n[bold]Content:[/bold]\n{markdown_text}")


def display_stages(stages: list[dict[str, Any]]) -> None:
    """Display stages in a table, TSV, or JSON format.

    Args:
        stages: List of stage dictionaries

    """
    if is_structured_output():
        structured_print(stages)
        return

    if _is_simple_output():
        write("id\tname\tsequence\tfold")
        for stage in stages:
            fold = "true" if stage.get("fold") else "false"
            write(f"{stage['id']}\t{stage['name']}\t{stage.get('sequence', '')}\t{fold}")
    else:
        from rich.table import Table

        console = _get_console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Sequence", justify="right")
        table.add_column("Folded", justify="center")

        for stage in stages:
            table.add_row(
                str(stage["id"]),
                stage["name"],
                str(stage.get("sequence", "")),
                "✓" if stage.get("fold") else "",
            )

        console.print(table)


__all__ = [
    "display_article_detail",
    "display_attachments",
    "display_crm_stages",
    "display_messages",
    "display_pipeline",
    "display_record_detail",
    "display_records",
    "display_stages",
    "display_tags",
]
